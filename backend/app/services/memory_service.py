import json
import re

from app.core.config import settings
from app.core.prompts import build_memory_update_prompt, fallback_memory_update
from app.models.chat import (
    MemoryConflict,
    MemoryFact,
    SessionMemory,
    SessionMemoryUpdate,
    SessionMessage,
    UserMemory,
    UserMemoryCandidateCreate,
    UserMemorySyncPlan,
    UserMemoryUpdate,
)
from app.services.llm_service import llm_service


STABLE_MEMORY_KEYS = {
    "target_role",
    "primary_stack",
    "project_experience",
    "constraint",
    "preference",
    "job_search_stage",
}

TEMPORARY_MEMORY_KEYS = {
    "current_focus",
    "current_plan",
    "active_application",
    "job_search_stage",
    "constraint",
}

LONG_TERM_MEMORY_KEYS = {
    "target_role",
    "primary_stack",
    "project_experience",
    "constraint",
    "preference",
    "job_search_stage",
}

CORRECTION_MARKERS = (
    "纠正一下",
    "更正一下",
    "不是",
    "不再",
    "改成",
    "现在改为",
    "现在主要",
    "转向",
    "转前端",
    "转后端",
    "actually",
    "instead",
)


class MemoryService:
    def should_refresh_memory(
        self,
        messages: list[SessionMessage],
        has_memory: bool,
        current_memory: SessionMemory | None = None,
    ) -> bool:
        user_message_count = sum(1 for message in messages if message.role == "user")
        assistant_message_count = sum(
            1 for message in messages if message.role == "assistant"
        )

        if user_message_count < 2 or assistant_message_count < 1:
            return False

        if not has_memory:
            return True

        if current_memory is None:
            return assistant_message_count % 2 == 0

        if current_memory.confidence < 0.65:
            return True

        latest_user = next(
            (message.content for message in reversed(messages) if message.role == "user"),
            "",
        )
        if self._contains_correction_signal(latest_user):
            return True

        if llm_service.should_auto_analyze_jd(latest_user):
            return True

        if assistant_message_count % 3 == 0:
            return True

        return False

    def build_memory_update(self, messages: list[SessionMessage]) -> SessionMemoryUpdate:
        if settings.mock_llm:
            return self._mock_memory_update(messages)

        history_lines = []
        user_turn = 0
        turn_map: list[int] = []

        for message in messages[-settings.chat_context_message_limit :]:
            if message.role == "user":
                user_turn += 1
                role = f"用户第{user_turn}轮"
                turn_map.append(user_turn)
            elif message.role == "assistant":
                role = "助手"
            else:
                role = "系统"
            history_lines.append(f"{role}: {message.content}")

        response = llm_service.client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": build_memory_update_prompt()},
                {"role": "user", "content": "\n".join(history_lines)},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        raw_reply = response.choices[0].message.content or ""

        try:
            parsed = json.loads(raw_reply)
            update = SessionMemoryUpdate.model_validate(parsed)
        except Exception:
            return fallback_memory_update()

        if update.source_turn_start == 0 and turn_map:
            update.source_turn_start = turn_map[0]
        if update.source_turn_end == 0 and turn_map:
            update.source_turn_end = turn_map[-1]
        return self._normalize_candidate(update)

    def merge_memory(
        self,
        current_memory: SessionMemory | None,
        candidate_memory: SessionMemoryUpdate,
        latest_user_message: str,
    ) -> SessionMemoryUpdate:
        if current_memory is None:
            return self._normalize_candidate(candidate_memory)

        merged = candidate_memory.model_copy(deep=True)
        candidate_stable_profile = list(candidate_memory.stable_profile)
        candidate_temporary_state = list(candidate_memory.temporary_state)
        merged.stable_profile = self._merge_fact_group(
            current_memory.stable_profile,
            candidate_memory.stable_profile,
            allow_newer_replace=self._contains_correction_signal(latest_user_message),
            category="stable",
        )
        merged.temporary_state = self._merge_fact_group(
            current_memory.temporary_state,
            candidate_memory.temporary_state,
            allow_newer_replace=True,
            category="temporary",
        )
        merged.conflicts = self._merge_conflicts(
            current_memory,
            candidate_stable_profile,
            candidate_temporary_state,
            merged.stable_profile,
            merged.temporary_state,
            candidate_memory.conflicts,
            latest_user_message,
        )

        if not merged.summary:
            merged.summary = current_memory.summary

        merged.confidence = max(
            current_memory.confidence,
            merged.confidence,
            self._estimate_confidence(merged.stable_profile + merged.temporary_state),
        )
        merged.source_turn_start = (
            current_memory.source_turn_start
            if current_memory.source_turn_start
            else merged.source_turn_start
        )
        merged.source_turn_end = max(
            current_memory.source_turn_end,
            merged.source_turn_end,
        )
        merged.user_profile = [
            f"{item.label}: {item.value}" for item in merged.stable_profile[:5]
        ]
        return merged

    def build_user_memory_sync_plan(
        self,
        session_id: str,
        user_id: str,
        session_memory: SessionMemory,
        current_user_memory: UserMemory | None = None,
    ) -> UserMemorySyncPlan:
        direct_candidates: list[MemoryFact] = []
        pending_candidates: list[UserMemoryCandidateCreate] = []

        current_map = {
            item.key: item
            for item in (current_user_memory.stable_profile if current_user_memory else [])
        }

        for item in session_memory.stable_profile:
            if item.key not in LONG_TERM_MEMORY_KEYS:
                continue
            if item.source_turn_end < max(1, item.source_turn_start):
                continue
            if item.source_type not in {"user", "manual"}:
                continue

            previous = current_map.get(item.key)
            if previous and self._is_same_fact_value(previous.value, item.value):
                if item.confidence >= previous.confidence + 0.05:
                    direct_candidates.append(item.model_copy(update={"scope": "user"}))
                continue

            decision = self._classify_long_term_candidate(previous, item)
            if decision["mode"] == "skip":
                continue

            normalized_item = item.model_copy(update={"scope": "user"})
            if decision["mode"] == "direct":
                direct_candidates.append(normalized_item)
                continue

            pending_candidates.append(
                UserMemoryCandidateCreate(
                    user_id=user_id,
                    session_id=session_id,
                    key=normalized_item.key,
                    label=normalized_item.label,
                    value=normalized_item.value,
                    previous_value=previous.value if previous else "",
                    scope="user",
                    source_type=normalized_item.source_type,
                    status="pending_confirmation",
                    reason=decision["reason"],
                    confidence=normalized_item.confidence,
                    source_turn_start=normalized_item.source_turn_start,
                    source_turn_end=normalized_item.source_turn_end,
                )
            )

        merged_stable_profile = (
            self._build_next_user_stable_profile(
                current_user_memory.stable_profile if current_user_memory else [],
                direct_candidates,
            )
            if direct_candidates or current_user_memory
            else []
        )

        next_conflicts = self._build_next_user_conflicts(
            current_user_memory=current_user_memory,
            direct_candidates=direct_candidates,
            pending_candidates=pending_candidates,
        )

        memory_update: UserMemoryUpdate | None = None
        if direct_candidates or next_conflicts != (
            current_user_memory.conflicts if current_user_memory else []
        ):
            summary = session_memory.summary or (
                current_user_memory.summary if current_user_memory else ""
            )
            confidence = max(
                current_user_memory.confidence if current_user_memory else 0.0,
                self._estimate_confidence(merged_stable_profile),
            )
            memory_update = UserMemoryUpdate(
                summary=summary,
                user_profile=[
                    f"{item.label}: {item.value}" for item in merged_stable_profile[:5]
                ],
                stable_profile=merged_stable_profile[:5],
                conflicts=next_conflicts[:5],
                confidence=confidence,
            )

        return UserMemorySyncPlan(memory=memory_update, candidates=pending_candidates[:10])

    def should_replace_user_memory(
        self,
        current_user_memory: UserMemory | None,
        candidate_user_memory: UserMemoryUpdate | None,
    ) -> bool:
        if candidate_user_memory is None:
            return False

        if not candidate_user_memory.stable_profile and not candidate_user_memory.conflicts:
            return False

        if current_user_memory is None:
            return True

        if candidate_user_memory.conflicts:
            return True

        if len(candidate_user_memory.stable_profile) != len(
            current_user_memory.stable_profile
        ):
            return True

        if self._fact_fingerprint(candidate_user_memory.stable_profile) != self._fact_fingerprint(
            current_user_memory.stable_profile
        ):
            return True

        if self._conflict_fingerprint(candidate_user_memory.conflicts) != self._conflict_fingerprint(
            current_user_memory.conflicts
        ):
            return True

        if candidate_user_memory.confidence >= current_user_memory.confidence + 0.05:
            return True

        if not current_user_memory.summary and candidate_user_memory.summary:
            return True

        return False

    @staticmethod
    def should_replace_memory(
        current_memory: SessionMemory | None,
        candidate_memory: SessionMemoryUpdate,
    ) -> bool:
        if (
            not candidate_memory.summary
            and not candidate_memory.user_profile
            and not candidate_memory.stable_profile
            and not candidate_memory.temporary_state
            and not candidate_memory.conflicts
        ):
            return False

        if current_memory is None:
            return True

        if candidate_memory.conflicts:
            return True

        if candidate_memory.confidence >= current_memory.confidence + 0.05:
            return True

        if (
            candidate_memory.source_turn_end > current_memory.source_turn_end
            and candidate_memory.confidence >= max(0.55, current_memory.confidence - 0.05)
        ):
            return True

        if len(candidate_memory.temporary_state) != len(current_memory.temporary_state):
            return True

        if len(candidate_memory.stable_profile) != len(current_memory.stable_profile):
            return True

        if MemoryService._fact_fingerprint(
            candidate_memory.stable_profile
        ) != MemoryService._fact_fingerprint(current_memory.stable_profile):
            return True

        if MemoryService._fact_fingerprint(
            candidate_memory.temporary_state
        ) != MemoryService._fact_fingerprint(current_memory.temporary_state):
            return True

        if MemoryService._conflict_fingerprint(
            candidate_memory.conflicts
        ) != MemoryService._conflict_fingerprint(current_memory.conflicts):
            return True

        if not current_memory.summary and candidate_memory.summary:
            return True

        return False

    def build_candidate_conflict(
        self,
        current_user_memory: UserMemory | None,
        key: str,
        incoming_value: str,
        source_type: str = "manual",
        confidence: float = 1.0,
    ) -> MemoryConflict | None:
        if current_user_memory is None:
            return None

        previous = next(
            (item for item in current_user_memory.stable_profile if item.key == key),
            None,
        )
        if previous is None or self._is_same_fact_value(previous.value, incoming_value):
            return None

        return MemoryConflict(
            key=key,
            label=previous.label,
            previous_value=previous.value,
            incoming_value=incoming_value,
            scope="user",
            source_type=source_type,
            status="resolved",
            resolution="manual override applied",
            confidence=max(previous.confidence, confidence),
        )

    def _mock_memory_update(self, messages: list[SessionMessage]) -> SessionMemoryUpdate:
        stable_profile: list[MemoryFact] = []
        temporary_state: list[MemoryFact] = []
        conflicts: list[MemoryConflict] = []
        turn_count = 0

        latest_focus = None
        correction_detected = False

        for message in messages[-settings.chat_context_message_limit :]:
            if message.role != "user":
                continue

            turn_count += 1
            content = message.content.strip()
            normalized = content.lower()

            if "后端开发实习" in content:
                stable_profile.append(
                    MemoryFact(
                        key="target_role",
                        label="目标岗位",
                        value="后端开发实习",
                        scope="session",
                        source_type="user",
                        confidence=0.93,
                        source_turn_start=turn_count,
                        source_turn_end=turn_count,
                    )
                )

            if "java" in normalized or "spring boot" in normalized or "mysql" in normalized:
                stable_profile.append(
                    MemoryFact(
                        key="primary_stack",
                        label="主技术栈",
                        value="Java, Spring Boot, MySQL",
                        scope="session",
                        source_type="user",
                        confidence=0.91,
                        source_turn_start=turn_count,
                        source_turn_end=turn_count,
                    )
                )

            if "秒杀系统" in content:
                stable_profile.append(
                    MemoryFact(
                        key="project_experience",
                        label="项目经历标签",
                        value="秒杀系统项目",
                        scope="session",
                        source_type="user",
                        confidence=0.88,
                        source_turn_start=turn_count,
                        source_turn_end=turn_count,
                    )
                )

            if "redis" in normalized and "操作系统" in content:
                latest_focus = "Redis、操作系统、计网"

            if "消息队列" in content or "linux" in normalized:
                latest_focus = "消息队列和 Linux"

            if "纠正一下" in content:
                correction_detected = True

        if latest_focus:
            temporary_state.append(
                MemoryFact(
                    key="current_focus",
                    label="当前重点",
                    value=latest_focus,
                    scope="session",
                    source_type="user",
                    confidence=0.9,
                    source_turn_start=max(1, turn_count - 1),
                    source_turn_end=turn_count,
                )
            )

        if correction_detected:
            conflicts.append(
                MemoryConflict(
                    key="current_focus",
                    label="当前重点",
                    previous_value="Redis、操作系统、计网",
                    incoming_value="消息队列和 Linux",
                    scope="session",
                    source_type="user",
                    status="resolved",
                    resolution="用户最近一轮明确纠正了短期重点",
                    confidence=0.9,
                    source_turn_start=max(1, turn_count - 1),
                    source_turn_end=turn_count,
                )
            )

        stable_profile = self._dedupe_facts(stable_profile)
        temporary_state = self._dedupe_facts(temporary_state)

        return SessionMemoryUpdate(
            summary="用户正在准备后端开发实习，已提供技术栈、项目经历和当前复习重点。",
            user_profile=[f"{item.label}: {item.value}" for item in stable_profile[:5]],
            stable_profile=stable_profile[:5],
            temporary_state=temporary_state[:5],
            conflicts=conflicts[:5],
            confidence=0.9,
            source_turn_start=1 if turn_count else 0,
            source_turn_end=turn_count,
        )

    def _merge_fact_group(
        self,
        current_items: list[MemoryFact],
        candidate_items: list[MemoryFact],
        allow_newer_replace: bool,
        category: str,
    ) -> list[MemoryFact]:
        merged: dict[str, MemoryFact] = {item.key: item for item in current_items}

        for item in candidate_items:
            normalized = item
            if category == "stable" and normalized.key not in STABLE_MEMORY_KEYS:
                continue
            if category == "temporary" and normalized.key not in TEMPORARY_MEMORY_KEYS:
                normalized = normalized.model_copy(
                    update={"key": "current_focus", "label": "当前重点"}
                )

            existing = merged.get(normalized.key)
            if existing is None:
                merged[normalized.key] = normalized
                continue

            if self._should_replace_fact(existing, normalized, allow_newer_replace):
                merged[normalized.key] = normalized

        return list(merged.values())[:5]

    def _merge_conflicts(
        self,
        current_memory: SessionMemory,
        candidate_stable_profile: list[MemoryFact],
        candidate_temporary_state: list[MemoryFact],
        stable_profile: list[MemoryFact],
        temporary_state: list[MemoryFact],
        candidate_conflicts: list[MemoryConflict],
        latest_user_message: str,
    ) -> list[MemoryConflict]:
        conflict_map: dict[str, MemoryConflict] = {
            item.key: item for item in current_memory.conflicts
        }
        correction_mode = self._contains_correction_signal(latest_user_message)

        stable_map = {item.key: item for item in stable_profile}
        raw_candidate_stable_map = {item.key: item for item in candidate_stable_profile}
        current_stable_map = {item.key: item for item in current_memory.stable_profile}

        for key, candidate in raw_candidate_stable_map.items():
            previous = current_stable_map.get(key)
            if previous is None or self._is_same_fact_value(previous.value, candidate.value):
                continue

            if self._should_ignore_conflict(previous, candidate):
                continue

            if correction_mode and self._is_message_targeting_change(
                latest_user_message,
                candidate,
                previous,
            ):
                conflict_map[key] = MemoryConflict(
                    key=key,
                    label=candidate.label,
                    previous_value=previous.value,
                    incoming_value=candidate.value,
                    scope="session",
                    source_type=candidate.source_type,
                    status="resolved",
                    resolution="latest user turn explicitly corrected this fact",
                    confidence=max(previous.confidence, candidate.confidence),
                    source_turn_start=candidate.source_turn_start,
                    source_turn_end=candidate.source_turn_end,
                )
                continue

            merged_candidate = stable_map.get(key, candidate)
            if self._is_same_fact_value(merged_candidate.value, candidate.value) and (
                candidate.confidence >= previous.confidence + 0.12
            ):
                conflict_map[key] = MemoryConflict(
                    key=key,
                    label=candidate.label,
                    previous_value=previous.value,
                    incoming_value=candidate.value,
                    scope="session",
                    source_type=candidate.source_type,
                    status="resolved",
                    resolution="newer fact replaced the older stable session fact",
                    confidence=candidate.confidence,
                    source_turn_start=candidate.source_turn_start,
                    source_turn_end=candidate.source_turn_end,
                )
                continue

            conflict_map[key] = MemoryConflict(
                key=key,
                label=candidate.label,
                previous_value=previous.value,
                incoming_value=candidate.value,
                scope="session",
                source_type=candidate.source_type,
                status="pending",
                resolution="session conflict detected; keep observing before replacing",
                confidence=max(previous.confidence, candidate.confidence),
                source_turn_start=candidate.source_turn_start,
                source_turn_end=candidate.source_turn_end,
            )

        for item in candidate_conflicts:
            conflict_map[item.key] = item

        temp_keys = {item.key for item in temporary_state} | {
            item.key for item in candidate_temporary_state
        }
        for key, item in list(conflict_map.items()):
            if item.status == "pending" and key in temp_keys and correction_mode:
                conflict_map[key] = item.model_copy(
                    update={
                        "status": "resolved",
                        "resolution": "latest user turn resolved the temporary conflict",
                    }
                )

        return list(conflict_map.values())[:5]

    def _build_next_user_stable_profile(
        self,
        existing_items: list[MemoryFact],
        direct_candidates: list[MemoryFact],
    ) -> list[MemoryFact]:
        merged = {item.key: item for item in existing_items}
        for candidate in direct_candidates:
            previous = merged.get(candidate.key)
            if previous is None or self._should_replace_fact(previous, candidate, True):
                merged[candidate.key] = candidate
        return list(merged.values())[:5]

    def _build_next_user_conflicts(
        self,
        current_user_memory: UserMemory | None,
        direct_candidates: list[MemoryFact],
        pending_candidates: list[UserMemoryCandidateCreate],
    ) -> list[MemoryConflict]:
        conflict_map: dict[str, MemoryConflict] = {
            item.key: item
            for item in (current_user_memory.conflicts if current_user_memory else [])
        }

        current_map = {
            item.key: item
            for item in (current_user_memory.stable_profile if current_user_memory else [])
        }

        for item in direct_candidates:
            previous = current_map.get(item.key)
            if previous is None or self._is_same_fact_value(previous.value, item.value):
                conflict_map.pop(item.key, None)
                continue
            conflict_map[item.key] = MemoryConflict(
                key=item.key,
                label=item.label,
                previous_value=previous.value,
                incoming_value=item.value,
                scope="user",
                source_type=item.source_type,
                status="resolved",
                resolution="auto merged into long-term memory",
                confidence=max(previous.confidence, item.confidence),
                source_turn_start=item.source_turn_start,
                source_turn_end=item.source_turn_end,
            )

        for item in pending_candidates:
            if not (item.previous_value or "").strip():
                continue
            conflict_map[item.key] = MemoryConflict(
                key=item.key,
                label=item.label,
                previous_value=item.previous_value,
                incoming_value=item.value,
                scope="user",
                source_type=item.source_type,
                status="pending",
                resolution=item.reason or "awaiting manual confirmation",
                confidence=item.confidence,
                source_turn_start=item.source_turn_start,
                source_turn_end=item.source_turn_end,
            )

        return list(conflict_map.values())[:5]

    def _classify_long_term_candidate(
        self,
        previous: MemoryFact | None,
        candidate: MemoryFact,
    ) -> dict[str, str]:
        if previous is None and candidate.confidence >= 0.92:
            return {"mode": "direct", "reason": "high confidence new stable fact"}

        if previous is None and candidate.confidence >= 0.8:
            if candidate.source_type == "manual":
                return {"mode": "candidate", "reason": "manual change to new long-term key requires confirmation"}
            return {"mode": "candidate", "reason": "new long-term fact needs confirmation"}

        if previous is None:
            return {"mode": "candidate", "reason": "confidence below safe auto-write threshold"}

        if self._is_same_fact_value(previous.value, candidate.value):
            if candidate.confidence >= previous.confidence + 0.05:
                return {"mode": "direct", "reason": "same fact with stronger confidence"}
            return {"mode": "skip", "reason": "same long-term fact already exists"}

        if candidate.source_type == "manual" and candidate.confidence >= 0.9:
            return {"mode": "candidate", "reason": "manual override conflicts with existing long-term memory"}

        if candidate.confidence >= previous.confidence + 0.2 and candidate.confidence >= 0.95:
            return {"mode": "direct", "reason": "incoming fact is much stronger than previous"}

        return {"mode": "candidate", "reason": "conflicts with existing long-term memory"}

    @staticmethod
    def _should_replace_fact(
        existing: MemoryFact,
        candidate: MemoryFact,
        allow_newer_replace: bool,
    ) -> bool:
        if MemoryService._is_same_fact_value(candidate.value, existing.value):
            return candidate.confidence >= existing.confidence or (
                candidate.source_turn_end >= existing.source_turn_end
            )

        if allow_newer_replace and candidate.source_turn_end > existing.source_turn_end:
            return True

        if candidate.confidence >= existing.confidence + 0.12:
            return True

        return False

    @staticmethod
    def _normalize_candidate(candidate: SessionMemoryUpdate) -> SessionMemoryUpdate:
        candidate.stable_profile = [
            item.model_copy(update={"scope": "session", "source_type": item.source_type})
            for item in candidate.stable_profile
            if item.key in STABLE_MEMORY_KEYS
        ][:5]
        candidate.temporary_state = [
            (
                item.model_copy(update={"scope": "session", "source_type": item.source_type})
                if item.key in TEMPORARY_MEMORY_KEYS
                else item.model_copy(
                    update={
                        "key": "current_focus",
                        "label": "当前重点",
                        "scope": "session",
                    }
                )
            )
            for item in candidate.temporary_state
        ][:5]
        candidate.conflicts = [
            item.model_copy(update={"scope": "session", "source_type": item.source_type})
            for item in candidate.conflicts[:5]
        ]
        candidate.user_profile = [
            f"{item.label}: {item.value}" for item in candidate.stable_profile[:5]
        ]
        return candidate

    @staticmethod
    def _contains_correction_signal(message: str) -> bool:
        normalized = message.strip()
        return any(marker in normalized for marker in CORRECTION_MARKERS)

    @staticmethod
    def _fact_fingerprint(items: list[MemoryFact]) -> list[tuple[str, str, str]]:
        return sorted(
            (item.key, item.label, MemoryService._canonicalize_fact_value(item.value))
            for item in items
        )

    @staticmethod
    def _conflict_fingerprint(
        items: list[MemoryConflict],
    ) -> list[tuple[str, str, str, str]]:
        return sorted(
            (
                item.key,
                MemoryService._canonicalize_fact_value(item.previous_value),
                MemoryService._canonicalize_fact_value(item.incoming_value),
                item.status,
            )
            for item in items
        )

    @staticmethod
    def _canonicalize_fact_value(value: str) -> str:
        normalized = value.strip().lower()
        normalized = normalized.replace("：", ":").replace("，", ",").replace("；", ";")
        normalized = normalized.replace("（", "(").replace("）", ")")
        normalized = normalized.replace(" ", "")
        normalized = re.sub(r"(实习生?)$", "实习", normalized)
        normalized = normalized.replace("项目经验", "项目经历")
        normalized = re.sub(r"\(.*?\)", "", normalized)
        normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff,]+", "", normalized)
        normalized = normalized.strip(",;: ")
        return normalized

    @staticmethod
    def _is_same_fact_value(left: str, right: str) -> bool:
        return MemoryService._canonicalize_fact_value(left) == MemoryService._canonicalize_fact_value(
            right
        )

    @staticmethod
    def _should_ignore_conflict(previous: MemoryFact, candidate: MemoryFact) -> bool:
        if previous.key != candidate.key:
            return False

        left = MemoryService._canonicalize_fact_value(previous.value)
        right = MemoryService._canonicalize_fact_value(candidate.value)
        if left == right:
            return True

        if previous.key == "project_experience" and (left in right or right in left):
            return True

        if previous.key == "target_role" and (left in right or right in left):
            return True

        return False

    @staticmethod
    def _is_message_targeting_change(
        message: str,
        candidate: MemoryFact,
        previous: MemoryFact,
    ) -> bool:
        normalized = message.strip()
        return (
            candidate.label in normalized
            or previous.value in normalized
            or candidate.value in normalized
        )

    @staticmethod
    def _estimate_confidence(items: list[MemoryFact]) -> float:
        scores = [item.confidence for item in items]
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 2)

    @staticmethod
    def _dedupe_facts(items: list[MemoryFact]) -> list[MemoryFact]:
        merged: dict[str, MemoryFact] = {}
        for item in items:
            existing = merged.get(item.key)
            if existing is None or item.confidence >= existing.confidence:
                merged[item.key] = item
        return list(merged.values())


memory_service = MemoryService()
