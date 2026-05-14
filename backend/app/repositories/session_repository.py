from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from app.core.config import settings
from app.db.database import database
from app.models.chat import (
    AuthVerificationCode,
    UserProfile,
    ChatStructuredReply,
    MemoryConflict,
    MemoryFact,
    SessionDetail,
    SessionMemory,
    SessionMemoryUpdate,
    SessionMessage,
    SessionSummary,
    ToolCallRecord,
    ToolExecutionLog,
    ToolExecutionLogCreate,
    UserMemory,
    UserMemoryCandidate,
    UserMemoryCandidateCreate,
    UserMemoryUpdate,
)


class SessionRepository:
    @staticmethod
    def _is_broken_text(text: str) -> bool:
        visible_chars = [char for char in text if not char.isspace()]
        if not visible_chars:
            return False

        broken_chars = sum(1 for char in visible_chars if char in {"?", "\ufffd"})
        return broken_chars / len(visible_chars) >= 0.3

    @staticmethod
    def _normalize_text(value: str, fallback: str) -> str:
        text = value.strip()
        if not text:
            return fallback

        repaired = SessionRepository._try_repair_mojibake(text)
        if repaired and repaired != text:
            text = repaired

        if "?" not in text and "\ufffd" not in text:
            return text

        if SessionRepository._is_broken_text(text):
            return fallback

        return text

    @staticmethod
    def _try_repair_mojibake(text: str) -> str | None:
        try:
            repaired = text.encode("latin-1").decode("utf-8")
        except Exception:
            return None

        repaired = repaired.strip()
        return repaired or None

    @staticmethod
    def _parse_structured_content(value: str | None) -> ChatStructuredReply | None:
        if not value:
            return None

        try:
            return ChatStructuredReply.model_validate_json(value)
        except Exception:
            return None

    @staticmethod
    def _parse_tool_calls(value: str | None) -> list[ToolCallRecord]:
        if not value:
            return []

        try:
            payload = json.loads(value)
        except Exception:
            return []

        if not isinstance(payload, list):
            return []

        tool_calls: list[ToolCallRecord] = []
        for item in payload:
            try:
                tool_calls.append(ToolCallRecord.model_validate(item))
            except Exception:
                continue
        return tool_calls

    @staticmethod
    def _parse_string_list(value: str | None) -> list[str]:
        if not value:
            return []

        try:
            items = json.loads(value)
        except Exception:
            return []

        if not isinstance(items, list):
            return []

        return [str(item).strip() for item in items if str(item).strip()]

    @staticmethod
    def _parse_memory_facts(value: str | None) -> list[MemoryFact]:
        if not value:
            return []

        try:
            payload = json.loads(value)
        except Exception:
            return []

        if not isinstance(payload, list):
            return []

        items: list[MemoryFact] = []
        for item in payload:
            try:
                items.append(MemoryFact.model_validate(item))
            except Exception:
                continue
        return items

    @staticmethod
    def _parse_memory_conflicts(value: str | None) -> list[MemoryConflict]:
        if not value:
            return []

        try:
            payload = json.loads(value)
        except Exception:
            return []

        if not isinstance(payload, list):
            return []

        items: list[MemoryConflict] = []
        for item in payload:
            try:
                items.append(MemoryConflict.model_validate(item))
            except Exception:
                continue
        return items

    def clean_mojibake_texts(self) -> None:
        with database.connection() as connection:
            session_rows = connection.execute(
                "SELECT id, title FROM sessions"
            ).fetchall()
            for row in session_rows:
                repaired = self._try_repair_mojibake(row["title"]) or row["title"]
                cleaned = self._normalize_text(repaired, "新会话")
                if cleaned != row["title"]:
                    connection.execute(
                        "UPDATE sessions SET title = ? WHERE id = ?",
                        (cleaned, row["id"]),
                    )

            message_rows = connection.execute(
                "SELECT id, content, structured_content FROM messages"
            ).fetchall()
            for row in message_rows:
                repaired = self._try_repair_mojibake(row["content"]) or row["content"]
                cleaned = self._normalize_text(repaired, "内容异常，请重新发送消息。")
                structured_content = row["structured_content"]
                if structured_content:
                    repaired_structured = (
                        self._try_repair_mojibake(structured_content) or structured_content
                    )
                    try:
                        structured_model = ChatStructuredReply.model_validate_json(
                            repaired_structured
                        )
                        structured_content = json.dumps(
                            structured_model.model_dump(mode="json"),
                            ensure_ascii=False,
                        )
                    except Exception:
                        structured_content = None

                if cleaned != row["content"] or structured_content != row["structured_content"]:
                    connection.execute(
                        "UPDATE messages SET content = ?, structured_content = ? WHERE id = ?",
                        (cleaned, structured_content, row["id"]),
                    )

            self._clean_memory_table(connection, table_name="session_memory", id_column="session_id")
            self._clean_memory_table(connection, table_name="user_memory", id_column="user_id")
            self._clean_candidate_table(connection)

    def _clean_memory_table(
        self,
        connection,
        table_name: str,
        id_column: str,
    ) -> None:
        has_temporary_state = table_name == "session_memory"
        selected_columns = [
            id_column,
            "summary",
            "user_profile_json",
            "stable_profile_json",
            "conflicts_json",
        ]
        if has_temporary_state:
            selected_columns.insert(4, "temporary_state_json")

        rows = connection.execute(
            f"""
            SELECT {", ".join(selected_columns)}
            FROM {table_name}
            """
        ).fetchall()

        for row in rows:
            repaired_summary = self._try_repair_mojibake(row["summary"]) or row["summary"]
            repaired_profile = [
                self._try_repair_mojibake(item) or item
                for item in self._parse_string_list(row["user_profile_json"])
            ]
            stable_profile = [
                item.model_copy(
                    update={
                        "label": self._try_repair_mojibake(item.label) or item.label,
                        "value": self._try_repair_mojibake(item.value) or item.value,
                    }
                )
                for item in self._parse_memory_facts(row["stable_profile_json"])
            ]
            conflicts = [
                item.model_copy(
                    update={
                        "label": self._try_repair_mojibake(item.label) or item.label,
                        "previous_value": self._try_repair_mojibake(item.previous_value)
                        or item.previous_value,
                        "incoming_value": self._try_repair_mojibake(item.incoming_value)
                        or item.incoming_value,
                        "resolution": self._try_repair_mojibake(item.resolution)
                        or item.resolution,
                    }
                )
                for item in self._parse_memory_conflicts(row["conflicts_json"])
            ]

            if has_temporary_state:
                temporary_state = [
                    item.model_copy(
                        update={
                            "label": self._try_repair_mojibake(item.label) or item.label,
                            "value": self._try_repair_mojibake(item.value) or item.value,
                        }
                    )
                    for item in self._parse_memory_facts(row["temporary_state_json"])
                ]
                connection.execute(
                    f"""
                    UPDATE {table_name}
                    SET
                        summary = ?,
                        user_profile_json = ?,
                        stable_profile_json = ?,
                        temporary_state_json = ?,
                        conflicts_json = ?
                    WHERE {id_column} = ?
                    """,
                    (
                        repaired_summary,
                        json.dumps(repaired_profile, ensure_ascii=False),
                        json.dumps(
                            [item.model_dump(mode="json") for item in stable_profile],
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            [item.model_dump(mode="json") for item in temporary_state],
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            [item.model_dump(mode="json") for item in conflicts],
                            ensure_ascii=False,
                        ),
                        row[id_column],
                    ),
                )
            else:
                connection.execute(
                    f"""
                    UPDATE {table_name}
                    SET
                        summary = ?,
                        user_profile_json = ?,
                        stable_profile_json = ?,
                        conflicts_json = ?
                    WHERE {id_column} = ?
                    """,
                    (
                        repaired_summary,
                        json.dumps(repaired_profile, ensure_ascii=False),
                        json.dumps(
                            [item.model_dump(mode="json") for item in stable_profile],
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            [item.model_dump(mode="json") for item in conflicts],
                            ensure_ascii=False,
                        ),
                        row[id_column],
                    ),
                )

    def _clean_candidate_table(self, connection) -> None:
        rows = connection.execute(
            """
            SELECT
                id,
                label,
                value,
                previous_value,
                reason
            FROM user_memory_candidates
            """
        ).fetchall()

        for row in rows:
            connection.execute(
                """
                UPDATE user_memory_candidates
                SET label = ?, value = ?, previous_value = ?, reason = ?
                WHERE id = ?
                """,
                (
                    self._try_repair_mojibake(row["label"]) or row["label"],
                    self._try_repair_mojibake(row["value"]) or row["value"],
                    self._try_repair_mojibake(row["previous_value"]) or row["previous_value"],
                    self._try_repair_mojibake(row["reason"]) or row["reason"],
                    row["id"],
                ),
            )

    def create_session(self, title: str, user_id: str | None = None) -> SessionDetail:
        now = datetime.now(UTC)
        session_id = str(uuid4())
        normalized_user_id = user_id or settings.default_user_id

        with database.connection() as connection:
            connection.execute(
                """
                INSERT INTO sessions (id, user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    normalized_user_id,
                    title,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

        return SessionDetail(
            id=session_id,
            user_id=normalized_user_id,
            title=title,
            created_at=now,
            updated_at=now,
            messages=[],
            memory=None,
        )

    def get_user_by_id(self, user_id: str) -> UserProfile | None:
        with database.connection() as connection:
            row = connection.execute(
                """
                SELECT id, phone, display_name, status, created_at, updated_at
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

        if row is None:
            return None

        return UserProfile(
            id=row["id"],
            phone=row["phone"],
            display_name=row["display_name"],
            status=row["status"] or "active",
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def get_user_by_phone(self, phone: str) -> UserProfile | None:
        with database.connection() as connection:
            row = connection.execute(
                """
                SELECT id, phone, display_name, status, created_at, updated_at
                FROM users
                WHERE phone = ?
                """,
                (phone,),
            ).fetchone()

        if row is None:
            return None

        return UserProfile(
            id=row["id"],
            phone=row["phone"],
            display_name=row["display_name"],
            status=row["status"] or "active",
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def create_user(
        self,
        *,
        phone: str,
        display_name: str,
    ) -> UserProfile:
        now = datetime.now(UTC)
        user_id = str(uuid4())

        with database.connection() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    id,
                    phone,
                    display_name,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, 'active', ?, ?)
                """,
                (
                    user_id,
                    phone,
                    display_name,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

        return UserProfile(
            id=user_id,
            phone=phone,
            display_name=display_name,
            status="active",
            created_at=now,
            updated_at=now,
        )

    def create_auth_verification_code(
        self,
        *,
        phone: str,
        purpose: str,
        code_hash: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> AuthVerificationCode:
        code_id = str(uuid4())

        with database.connection() as connection:
            connection.execute(
                """
                INSERT INTO auth_verification_codes (
                    id,
                    phone,
                    purpose,
                    code_hash,
                    attempts,
                    status,
                    created_at,
                    expires_at,
                    consumed_at,
                    last_sent_at
                )
                VALUES (?, ?, ?, ?, 0, 'pending', ?, ?, NULL, ?)
                """,
                (
                    code_id,
                    phone,
                    purpose,
                    code_hash,
                    created_at.isoformat(),
                    expires_at.isoformat(),
                    created_at.isoformat(),
                ),
            )

        return AuthVerificationCode(
            id=code_id,
            phone=phone,
            purpose=purpose,
            attempts=0,
            status="pending",
            created_at=created_at,
            expires_at=expires_at,
            consumed_at=None,
            last_sent_at=created_at,
        )

    def get_latest_auth_verification_code(
        self,
        *,
        phone: str,
        purpose: str,
    ) -> AuthVerificationCode | None:
        with database.connection() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    phone,
                    purpose,
                    attempts,
                    status,
                    created_at,
                    expires_at,
                    consumed_at,
                    last_sent_at
                FROM auth_verification_codes
                WHERE phone = ? AND purpose = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (phone, purpose),
            ).fetchone()

        if row is None:
            return None

        return AuthVerificationCode(
            id=row["id"],
            phone=row["phone"],
            purpose=row["purpose"],
            attempts=int(row["attempts"] or 0),
            status=row["status"] or "pending",
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            consumed_at=(
                datetime.fromisoformat(row["consumed_at"]) if row["consumed_at"] else None
            ),
            last_sent_at=datetime.fromisoformat(row["last_sent_at"]),
        )

    def get_auth_code_hash(self, code_id: str) -> str | None:
        with database.connection() as connection:
            row = connection.execute(
                """
                SELECT code_hash
                FROM auth_verification_codes
                WHERE id = ?
                """,
                (code_id,),
            ).fetchone()

        if row is None:
            return None
        return row["code_hash"] or None

    def increment_auth_code_attempts(self, code_id: str, attempts: int) -> None:
        with database.connection() as connection:
            connection.execute(
                """
                UPDATE auth_verification_codes
                SET attempts = ?
                WHERE id = ?
                """,
                (attempts, code_id),
            )

    def mark_auth_code_consumed(
        self,
        code_id: str,
        *,
        status: str,
        consumed_at: datetime,
    ) -> None:
        with database.connection() as connection:
            connection.execute(
                """
                UPDATE auth_verification_codes
                SET status = ?, consumed_at = ?
                WHERE id = ?
                """,
                (status, consumed_at.isoformat(), code_id),
            )

    def get_session(self, session_id: str) -> SessionDetail | None:
        with database.connection() as connection:
            session_row = connection.execute(
                """
                SELECT id, user_id, title, created_at, updated_at
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()

            if session_row is None:
                return None

            memory_row = connection.execute(
                """
                SELECT
                    session_id,
                    summary,
                    user_profile_json,
                    stable_profile_json,
                    temporary_state_json,
                    conflicts_json,
                    confidence,
                    source_turn_start,
                    source_turn_end,
                    updated_at
                FROM session_memory
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

            message_rows = connection.execute(
                """
                SELECT role, content, structured_content, tool_calls_json
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            ).fetchall()

        memory = None
        if memory_row is not None:
            stable_profile = self._normalize_memory_facts(memory_row["stable_profile_json"])
            temporary_state = self._normalize_memory_facts(memory_row["temporary_state_json"])
            conflicts = self._normalize_memory_conflicts(memory_row["conflicts_json"])
            memory = SessionMemory(
                session_id=memory_row["session_id"],
                summary=self._normalize_text(memory_row["summary"], ""),
                user_profile=[
                    self._normalize_text(item, item)
                    for item in self._parse_string_list(memory_row["user_profile_json"])
                ],
                stable_profile=stable_profile,
                temporary_state=temporary_state,
                conflicts=conflicts,
                confidence=float(memory_row["confidence"] or 0),
                source_turn_start=int(memory_row["source_turn_start"] or 0),
                source_turn_end=int(memory_row["source_turn_end"] or 0),
                updated_at=datetime.fromisoformat(memory_row["updated_at"]),
            )

        messages: list[SessionMessage] = []
        for row in message_rows:
            normalized_content = self._normalize_text(row["content"], "")
            if not normalized_content:
                continue

            messages.append(
                SessionMessage(
                    role=row["role"],
                    content=normalized_content,
                    structured=self._parse_structured_content(row["structured_content"]),
                    tool_calls=self._parse_tool_calls(row["tool_calls_json"]),
                )
            )

        return SessionDetail(
            id=session_row["id"],
            user_id=session_row["user_id"] or settings.default_user_id,
            title=self._normalize_text(session_row["title"], "新会话"),
            created_at=datetime.fromisoformat(session_row["created_at"]),
            updated_at=datetime.fromisoformat(session_row["updated_at"]),
            messages=messages,
            memory=memory,
        )

    def list_sessions(self, user_id: str | None = None) -> list[SessionSummary]:
        normalized_user_id = user_id or settings.default_user_id
        with database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    s.id,
                    s.user_id,
                    s.title,
                    s.created_at,
                    s.updated_at,
                    COALESCE(
                        (
                            SELECT m.content
                            FROM messages m
                            WHERE m.session_id = s.id
                            ORDER BY m.created_at DESC, m.id DESC
                            LIMIT 1
                        ),
                        ''
                    ) AS last_message_preview
                FROM sessions s
                WHERE s.user_id = ?
                ORDER BY s.updated_at DESC, s.id DESC
                """,
                (normalized_user_id,),
            ).fetchall()

        return [
            SessionSummary(
                id=row["id"],
                user_id=row["user_id"] or settings.default_user_id,
                title=self._normalize_text(row["title"], "新会话"),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                last_message_preview=self._normalize_text(
                    row["last_message_preview"],
                    "内容异常，请重新发送消息。",
                ),
            )
            for row in rows
        ]

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        structured: ChatStructuredReply | None = None,
        tool_calls: list[ToolCallRecord] | None = None,
    ) -> None:
        now = datetime.now(UTC)
        structured_content = (
            json.dumps(structured.model_dump(), ensure_ascii=False)
            if structured
            else None
        )
        normalized_tool_calls = tool_calls or []

        with database.connection() as connection:
            connection.execute(
                """
                INSERT INTO messages (
                    id,
                    session_id,
                    role,
                    content,
                    structured_content,
                    tool_calls_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    session_id,
                    role,
                    content,
                    structured_content,
                    json.dumps(
                        [item.model_dump(mode="json") for item in normalized_tool_calls],
                        ensure_ascii=False,
                    ),
                    now.isoformat(),
                ),
            )
            connection.execute(
                """
                UPDATE sessions
                SET updated_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), session_id),
            )

    def upsert_memory(self, session_id: str, memory: SessionMemoryUpdate) -> SessionMemory:
        now = datetime.now(UTC)

        with database.connection() as connection:
            connection.execute(
                """
                INSERT INTO session_memory (
                    session_id,
                    summary,
                    user_profile_json,
                    stable_profile_json,
                    temporary_state_json,
                    conflicts_json,
                    confidence,
                    source_turn_start,
                    source_turn_end,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id)
                DO UPDATE SET
                    summary = excluded.summary,
                    user_profile_json = excluded.user_profile_json,
                    stable_profile_json = excluded.stable_profile_json,
                    temporary_state_json = excluded.temporary_state_json,
                    conflicts_json = excluded.conflicts_json,
                    confidence = excluded.confidence,
                    source_turn_start = excluded.source_turn_start,
                    source_turn_end = excluded.source_turn_end,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    memory.summary,
                    json.dumps(memory.user_profile, ensure_ascii=False),
                    json.dumps(
                        [item.model_dump(mode="json") for item in memory.stable_profile],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        [item.model_dump(mode="json") for item in memory.temporary_state],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        [item.model_dump(mode="json") for item in memory.conflicts],
                        ensure_ascii=False,
                    ),
                    memory.confidence,
                    memory.source_turn_start,
                    memory.source_turn_end,
                    now.isoformat(),
                ),
            )

        return SessionMemory(
            session_id=session_id,
            summary=memory.summary,
            user_profile=memory.user_profile,
            stable_profile=[
                item.model_copy(update={"updated_at": now}) for item in memory.stable_profile
            ],
            temporary_state=[
                item.model_copy(update={"updated_at": now})
                for item in memory.temporary_state
            ],
            conflicts=[
                item.model_copy(update={"updated_at": now}) for item in memory.conflicts
            ],
            confidence=memory.confidence,
            source_turn_start=memory.source_turn_start,
            source_turn_end=memory.source_turn_end,
            updated_at=now,
        )

    def get_user_memory(self, user_id: str) -> UserMemory | None:
        with database.connection() as connection:
            row = connection.execute(
                """
                SELECT
                    user_id,
                    summary,
                    user_profile_json,
                    stable_profile_json,
                    conflicts_json,
                    confidence,
                    updated_at
                FROM user_memory
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

        if row is None:
            return None

        return UserMemory(
            user_id=row["user_id"],
            summary=self._normalize_text(row["summary"], ""),
            user_profile=[
                self._normalize_text(item, item)
                for item in self._parse_string_list(row["user_profile_json"])
            ],
            stable_profile=self._normalize_memory_facts(row["stable_profile_json"]),
            conflicts=self._normalize_memory_conflicts(row["conflicts_json"]),
            confidence=float(row["confidence"] or 0),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def upsert_user_memory(self, user_id: str, memory: UserMemoryUpdate) -> UserMemory:
        now = datetime.now(UTC)

        with database.connection() as connection:
            connection.execute(
                """
                INSERT INTO user_memory (
                    user_id,
                    summary,
                    user_profile_json,
                    stable_profile_json,
                    conflicts_json,
                    confidence,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id)
                DO UPDATE SET
                    summary = excluded.summary,
                    user_profile_json = excluded.user_profile_json,
                    stable_profile_json = excluded.stable_profile_json,
                    conflicts_json = excluded.conflicts_json,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    memory.summary,
                    json.dumps(memory.user_profile, ensure_ascii=False),
                    json.dumps(
                        [item.model_dump(mode="json") for item in memory.stable_profile],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        [item.model_dump(mode="json") for item in memory.conflicts],
                        ensure_ascii=False,
                    ),
                    memory.confidence,
                    now.isoformat(),
                ),
            )

        return UserMemory(
            user_id=user_id,
            summary=memory.summary,
            user_profile=memory.user_profile,
            stable_profile=[
                item.model_copy(update={"updated_at": now}) for item in memory.stable_profile
            ],
            conflicts=[
                item.model_copy(update={"updated_at": now}) for item in memory.conflicts
            ],
            confidence=memory.confidence,
            updated_at=now,
        )

    def delete_user_memory_fact(self, user_id: str, key: str) -> UserMemory | None:
        current = self.get_user_memory(user_id)
        if current is None:
            return None

        stable_profile = [item for item in current.stable_profile if item.key != key]
        conflicts = [item for item in current.conflicts if item.key != key]

        update = UserMemoryUpdate(
            summary=current.summary,
            user_profile=[f"{item.label}: {item.value}" for item in stable_profile[:5]],
            stable_profile=stable_profile,
            conflicts=conflicts,
            confidence=current.confidence if stable_profile else 0.0,
        )
        return self.upsert_user_memory(user_id, update)

    def list_user_memory_candidates(
        self,
        user_id: str,
        status: str | None = None,
    ) -> list[UserMemoryCandidate]:
        with database.connection() as connection:
            if status:
                rows = connection.execute(
                    """
                    SELECT
                        id,
                        user_id,
                        session_id,
                        key,
                        label,
                        value,
                        previous_value,
                        scope,
                        source_type,
                        status,
                        reason,
                        confidence,
                        source_turn_start,
                        source_turn_end,
                        created_at,
                        updated_at
                    FROM user_memory_candidates
                    WHERE user_id = ? AND status = ?
                    ORDER BY updated_at DESC, id DESC
                    """,
                    (user_id, status),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT
                        id,
                        user_id,
                        session_id,
                        key,
                        label,
                        value,
                        previous_value,
                        scope,
                        source_type,
                        status,
                        reason,
                        confidence,
                        source_turn_start,
                        source_turn_end,
                        created_at,
                        updated_at
                    FROM user_memory_candidates
                    WHERE user_id = ?
                    ORDER BY updated_at DESC, id DESC
                    """,
                    (user_id,),
                ).fetchall()

        return [self._build_user_memory_candidate(row) for row in rows]

    def get_user_memory_candidate(
        self,
        candidate_id: str,
        user_id: str,
    ) -> UserMemoryCandidate | None:
        with database.connection() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    user_id,
                    session_id,
                    key,
                    label,
                    value,
                    previous_value,
                    scope,
                    source_type,
                    status,
                    reason,
                    confidence,
                    source_turn_start,
                    source_turn_end,
                    created_at,
                    updated_at
                FROM user_memory_candidates
                WHERE id = ? AND user_id = ?
                """,
                (candidate_id, user_id),
            ).fetchone()

        if row is None:
            return None
        return self._build_user_memory_candidate(row)

    def create_user_memory_candidate(
        self,
        candidate: UserMemoryCandidateCreate,
    ) -> UserMemoryCandidate:
        now = datetime.now(UTC)
        candidate_id = str(uuid4())

        with database.connection() as connection:
            connection.execute(
                """
                INSERT INTO user_memory_candidates (
                    id,
                    user_id,
                    session_id,
                    key,
                    label,
                    value,
                    previous_value,
                    scope,
                    source_type,
                    status,
                    reason,
                    confidence,
                    source_turn_start,
                    source_turn_end,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    candidate.user_id,
                    candidate.session_id,
                    candidate.key,
                    candidate.label,
                    candidate.value,
                    candidate.previous_value,
                    candidate.scope,
                    candidate.source_type,
                    candidate.status,
                    candidate.reason,
                    candidate.confidence,
                    candidate.source_turn_start,
                    candidate.source_turn_end,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

        return UserMemoryCandidate(
            id=candidate_id,
            user_id=candidate.user_id,
            session_id=candidate.session_id,
            key=candidate.key,
            label=candidate.label,
            value=candidate.value,
            previous_value=candidate.previous_value,
            scope=candidate.scope,
            source_type=candidate.source_type,
            status=candidate.status,
            reason=candidate.reason,
            confidence=candidate.confidence,
            source_turn_start=candidate.source_turn_start,
            source_turn_end=candidate.source_turn_end,
            created_at=now,
            updated_at=now,
        )

    def update_user_memory_candidate_status(
        self,
        candidate_id: str,
        user_id: str,
        status: str,
    ) -> UserMemoryCandidate | None:
        now = datetime.now(UTC)
        with database.connection() as connection:
            connection.execute(
                """
                UPDATE user_memory_candidates
                SET status = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (status, now.isoformat(), candidate_id, user_id),
            )

        return self.get_user_memory_candidate(candidate_id, user_id)

    def delete_pending_candidate_by_key(
        self,
        user_id: str,
        key: str,
    ) -> None:
        with database.connection() as connection:
            connection.execute(
                """
                DELETE FROM user_memory_candidates
                WHERE user_id = ? AND key = ? AND status = 'pending_confirmation'
                """,
                (user_id, key),
            )

    def create_tool_execution_log(
        self,
        user_id: str,
        session_id: str,
        log: ToolExecutionLogCreate,
    ) -> ToolExecutionLog:
        now = datetime.now(UTC)
        log_id = str(uuid4())

        with database.connection() as connection:
            connection.execute(
                """
                INSERT INTO tool_execution_logs (
                    id,
                    user_id,
                    session_id,
                    tool_name,
                    trigger,
                    status,
                    input_json,
                    output_json,
                    error_message,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    user_id,
                    session_id,
                    log.tool_name,
                    log.trigger,
                    log.status,
                    json.dumps(log.input_json, ensure_ascii=False),
                    json.dumps(log.output_json, ensure_ascii=False),
                    log.error_message,
                    now.isoformat(),
                ),
            )

        return ToolExecutionLog(
            id=log_id,
            user_id=user_id,
            session_id=session_id,
            tool_name=log.tool_name,
            trigger=log.trigger,
            status=log.status,
            input_json=log.input_json,
            output_json=log.output_json,
            error_message=log.error_message,
            created_at=now,
        )

    def list_tool_execution_logs(self, session_id: str) -> list[ToolExecutionLog]:
        with database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    user_id,
                    session_id,
                    tool_name,
                    trigger,
                    status,
                    input_json,
                    output_json,
                    error_message,
                    created_at
                FROM tool_execution_logs
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            ).fetchall()

        logs: list[ToolExecutionLog] = []
        for row in rows:
            try:
                input_json = json.loads(row["input_json"] or "{}")
            except Exception:
                input_json = {}

            try:
                output_json = json.loads(row["output_json"] or "{}")
            except Exception:
                output_json = {}

            logs.append(
                ToolExecutionLog(
                    id=row["id"],
                    user_id=row["user_id"],
                    session_id=row["session_id"],
                    tool_name=row["tool_name"],
                    trigger=row["trigger"],
                    status=row["status"],
                    input_json=input_json if isinstance(input_json, dict) else {},
                    output_json=output_json if isinstance(output_json, dict) else {},
                    error_message=row["error_message"] or "",
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
            )
        return logs

    @classmethod
    def _normalize_memory_facts(cls, value: str | None) -> list[MemoryFact]:
        return [
            item.model_copy(
                update={
                    "label": cls._normalize_text(item.label, item.label),
                    "value": cls._normalize_text(item.value, item.value),
                }
            )
            for item in cls._parse_memory_facts(value)
        ]

    @classmethod
    def _normalize_memory_conflicts(cls, value: str | None) -> list[MemoryConflict]:
        return [
            item.model_copy(
                update={
                    "label": cls._normalize_text(item.label, item.label),
                    "previous_value": cls._normalize_text(
                        item.previous_value, item.previous_value
                    ),
                    "incoming_value": cls._normalize_text(
                        item.incoming_value, item.incoming_value
                    ),
                    "resolution": cls._normalize_text(item.resolution, item.resolution),
                }
            )
            for item in cls._parse_memory_conflicts(value)
        ]

    @classmethod
    def _build_user_memory_candidate(cls, row) -> UserMemoryCandidate:
        return UserMemoryCandidate(
            id=row["id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            key=row["key"],
            label=cls._normalize_text(row["label"], row["label"]),
            value=cls._normalize_text(row["value"], row["value"]),
            previous_value=cls._normalize_text(
                row["previous_value"], row["previous_value"] or ""
            ),
            scope=row["scope"] or "user",
            source_type=row["source_type"] or "user",
            status=row["status"] or "pending_confirmation",
            reason=cls._normalize_text(row["reason"], row["reason"] or ""),
            confidence=float(row["confidence"] or 0),
            source_turn_start=int(row["source_turn_start"] or 0),
            source_turn_end=int(row["source_turn_end"] or 0),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


session_repository = SessionRepository()
