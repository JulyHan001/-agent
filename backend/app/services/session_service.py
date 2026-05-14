from __future__ import annotations

from fastapi import HTTPException

from app.core.config import settings
from app.models.chat import (
    ChatStructuredReply,
    MemoryFact,
    MemoryConflict,
    SessionDetail,
    SessionMemory,
    SessionMessage,
    SessionSummary,
    ToolCallRecord,
    ToolExecutionLog,
    ToolExecutionLogCreate,
    UserProfile,
    UserMemory,
    UserMemoryCandidate,
    UserMemoryFactRequest,
    UserMemoryUpdate,
)
from app.repositories.session_repository import session_repository
from app.services.memory_service import memory_service


class SessionService:
    def __init__(self) -> None:
        self._cleanup_completed = False

    def list_session_summaries(self, user_id: str | None = None) -> list[SessionSummary]:
        self._ensure_historical_cleanup()
        return session_repository.list_sessions(user_id=user_id)

    def get_session(self, session_id: str, user_id: str | None = None) -> SessionDetail:
        self._ensure_historical_cleanup()
        session = session_repository.get_session(session_id)

        if session is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        if user_id and session.user_id != user_id:
            raise HTTPException(status_code=404, detail="Session not found.")

        return session

    def ensure_session(
        self,
        session_id: str | None,
        first_user_message: str,
        user_id: str,
    ) -> SessionDetail:
        if session_id:
            return self.get_session(session_id, user_id=user_id)

        title = self._build_session_title(first_user_message)
        return session_repository.create_session(title=title, user_id=user_id)

    def append_user_message(self, session_id: str, content: str, user_id: str | None = None) -> None:
        if user_id:
            self.get_session(session_id, user_id=user_id)
        session_repository.add_message(session_id=session_id, role="user", content=content)

    def append_assistant_message(
        self,
        session_id: str,
        content: str,
        user_id: str | None = None,
        structured: ChatStructuredReply | None = None,
        tool_calls: list[ToolCallRecord] | None = None,
    ) -> None:
        if user_id:
            self.get_session(session_id, user_id=user_id)
        session_repository.add_message(
            session_id=session_id,
            role="assistant",
            content=content,
            structured=structured,
            tool_calls=tool_calls,
        )

    def record_tool_execution_logs(
        self,
        session_id: str,
        logs: list[ToolExecutionLogCreate],
        user_id: str | None = None,
    ) -> list[ToolExecutionLog]:
        if not logs:
            return []

        session = self.get_session(session_id, user_id=user_id)
        normalized_user_id = session.user_id or settings.default_user_id
        return [
            session_repository.create_tool_execution_log(normalized_user_id, session_id, item)
            for item in logs
        ]

    def list_tool_execution_logs(self, session_id: str, user_id: str | None = None) -> list[ToolExecutionLog]:
        self.get_session(session_id, user_id=user_id)
        return session_repository.list_tool_execution_logs(session_id)

    def build_context_messages(self, session_id: str, user_id: str | None = None) -> list[SessionMessage]:
        session = self.get_session(session_id, user_id=user_id)
        return session.messages[-settings.chat_context_message_limit :]

    def get_memory(self, session_id: str, user_id: str | None = None) -> SessionMemory | None:
        session = self.get_session(session_id, user_id=user_id)
        return session.memory

    def get_user_memory_by_session(self, session_id: str, user_id: str | None = None) -> UserMemory | None:
        session = self.get_session(session_id, user_id=user_id)
        if not session.user_id:
            return None
        return session_repository.get_user_memory(session.user_id)

    def get_user_memory(self, user_id: str | None = None) -> UserMemory | None:
        normalized_user_id = user_id or settings.default_user_id
        return session_repository.get_user_memory(normalized_user_id)

    def refresh_memory(self, session_id: str, user_id: str | None = None) -> SessionMemory | None:
        session = self.get_session(session_id, user_id=user_id)

        if not memory_service.should_refresh_memory(
            session.messages,
            has_memory=session.memory is not None,
            current_memory=session.memory,
        ):
            return session.memory

        memory_update = memory_service.build_memory_update(session.messages)
        latest_user_message = next(
            (message.content for message in reversed(session.messages) if message.role == "user"),
            "",
        )
        memory_update = memory_service.merge_memory(
            session.memory,
            memory_update,
            latest_user_message,
        )
        if not memory_service.should_replace_memory(session.memory, memory_update):
            return session.memory

        updated_memory = session_repository.upsert_memory(session_id, memory_update)
        self.refresh_user_memory_from_session(session.id, user_id=session.user_id, session_memory=updated_memory)
        return updated_memory

    def refresh_user_memory_from_session(
        self,
        session_id: str,
        user_id: str | None = None,
        session_memory: SessionMemory | None = None,
    ) -> UserMemory | None:
        session = self.get_session(session_id, user_id=user_id)
        if not session.user_id:
            return None

        normalized_session_memory = session_memory or session.memory
        if normalized_session_memory is None:
            return session_repository.get_user_memory(session.user_id)

        current_user_memory = session_repository.get_user_memory(session.user_id)
        sync_plan = memory_service.build_user_memory_sync_plan(
            session_id=session.id,
            user_id=session.user_id,
            session_memory=normalized_session_memory,
            current_user_memory=current_user_memory,
        )
        memory = current_user_memory

        if memory_service.should_replace_user_memory(current_user_memory, sync_plan.memory):
            memory = session_repository.upsert_user_memory(session.user_id, sync_plan.memory)

        for candidate in sync_plan.candidates:
            session_repository.delete_pending_candidate_by_key(session.user_id, candidate.key)
            session_repository.create_user_memory_candidate(candidate)

        return memory

    def list_user_memory_candidates(self, user_id: str | None = None) -> list[UserMemoryCandidate]:
        normalized_user_id = user_id or settings.default_user_id
        return session_repository.list_user_memory_candidates(
            normalized_user_id,
            status="pending_confirmation",
        )

    def approve_user_memory_candidate(
        self,
        candidate_id: str,
        user_id: str | None = None,
    ) -> tuple[UserMemoryCandidate, UserMemory | None]:
        normalized_user_id = user_id or settings.default_user_id
        candidate = session_repository.get_user_memory_candidate(candidate_id, normalized_user_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidate not found.")

        current = session_repository.get_user_memory(normalized_user_id)
        manual_fact = MemoryFact(
            key=candidate.key,
            label=candidate.label,
            value=candidate.value,
            scope="user",
            source_type="manual",
            confidence=max(candidate.confidence, 0.95),
            source_turn_start=candidate.source_turn_start,
            source_turn_end=candidate.source_turn_end,
        )

        existing_profile = current.stable_profile if current else []
        merged_profile = {item.key: item for item in existing_profile}
        merged_profile[manual_fact.key] = manual_fact

        conflicts = [item for item in (current.conflicts if current else []) if item.key != manual_fact.key]
        if candidate.previous_value:
            conflicts.append(
                MemoryConflict(
                    key=manual_fact.key,
                    label=manual_fact.label,
                    previous_value=candidate.previous_value,
                    incoming_value=manual_fact.value,
                    scope="user",
                    source_type="manual",
                    status="resolved",
                    resolution="candidate approved manually",
                    confidence=manual_fact.confidence,
                    source_turn_start=manual_fact.source_turn_start,
                    source_turn_end=manual_fact.source_turn_end,
                )
            )

        update = UserMemoryUpdate(
            summary=current.summary if current else "",
            user_profile=[
                f"{item.label}: {item.value}"
                for item in list(merged_profile.values())[:5]
            ],
            stable_profile=list(merged_profile.values())[:5],
            conflicts=conflicts[:5],
            confidence=max(current.confidence if current else 0.0, manual_fact.confidence),
        )
        memory = session_repository.upsert_user_memory(normalized_user_id, update)
        updated_candidate = session_repository.update_user_memory_candidate_status(
            candidate_id,
            normalized_user_id,
            "approved",
        )
        return updated_candidate or candidate, memory

    def reject_user_memory_candidate(
        self,
        candidate_id: str,
        user_id: str | None = None,
    ) -> tuple[UserMemoryCandidate, UserMemory | None]:
        normalized_user_id = user_id or settings.default_user_id
        candidate = session_repository.get_user_memory_candidate(candidate_id, normalized_user_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidate not found.")

        updated_candidate = session_repository.update_user_memory_candidate_status(
            candidate_id,
            normalized_user_id,
            "rejected",
        )
        return updated_candidate or candidate, session_repository.get_user_memory(normalized_user_id)

    def upsert_user_memory_fact(
        self,
        request: UserMemoryFactRequest,
        user_id: str | None = None,
    ) -> UserMemory:
        normalized_user_id = user_id or settings.default_user_id
        current = session_repository.get_user_memory(normalized_user_id)

        manual_fact = MemoryFact(
            key=request.key,
            label=request.label,
            value=request.value,
            scope="user",
            source_type="manual",
            confidence=request.confidence,
        )

        existing_profile = current.stable_profile if current else []
        merged_profile = {
            item.key: item for item in existing_profile
        }
        merged_profile[manual_fact.key] = manual_fact

        existing_conflicts = current.conflicts if current else []
        conflicts = [item for item in existing_conflicts if item.key != manual_fact.key]
        override_conflict = memory_service.build_candidate_conflict(
            current_user_memory=current,
            key=request.key,
            incoming_value=request.value,
            source_type="manual",
            confidence=request.confidence,
        )
        if override_conflict:
            conflicts.append(override_conflict)

        update = UserMemoryUpdate(
            summary=current.summary if current else "",
            user_profile=[
                f"{item.label}: {item.value}"
                for item in list(merged_profile.values())[:5]
            ],
            stable_profile=list(merged_profile.values())[:5],
            conflicts=conflicts[:5],
            confidence=max(current.confidence if current else 0.0, request.confidence),
        )
        memory = session_repository.upsert_user_memory(normalized_user_id, update)
        session_repository.delete_pending_candidate_by_key(normalized_user_id, request.key)
        return memory

    def delete_user_memory_fact(
        self,
        key: str,
        user_id: str | None = None,
    ) -> UserMemory | None:
        normalized_user_id = user_id or settings.default_user_id
        return session_repository.delete_user_memory_fact(normalized_user_id, key)

    def _ensure_historical_cleanup(self) -> None:
        if self._cleanup_completed:
            return

        session_repository.clean_mojibake_texts()
        self._cleanup_completed = True

    @staticmethod
    def _build_session_title(message: str) -> str:
        compact_message = " ".join(message.strip().split())
        if not compact_message:
            return "新会话"
        return compact_message[:30]


session_service = SessionService()
