from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings


class Database:
    def __init__(self, sqlite_path: str) -> None:
        self.path = Path(sqlite_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connection() as connection:
            user_columns_before_create = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    phone TEXT,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_verification_codes (
                    id TEXT PRIMARY KEY,
                    phone TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    last_sent_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS session_memory (
                    session_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL DEFAULT '',
                    user_profile_json TEXT NOT NULL DEFAULT '[]',
                    stable_profile_json TEXT NOT NULL DEFAULT '[]',
                    temporary_state_json TEXT NOT NULL DEFAULT '[]',
                    conflicts_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_memory (
                    user_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL DEFAULT '',
                    user_profile_json TEXT NOT NULL DEFAULT '[]',
                    stable_profile_json TEXT NOT NULL DEFAULT '[]',
                    conflicts_json TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_memory_candidates (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT,
                    key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    value TEXT NOT NULL,
                    previous_value TEXT NOT NULL DEFAULT '',
                    scope TEXT NOT NULL DEFAULT 'user',
                    source_type TEXT NOT NULL DEFAULT 'user',
                    status TEXT NOT NULL DEFAULT 'pending_confirmation',
                    reason TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0,
                    source_turn_start INTEGER NOT NULL DEFAULT 0,
                    source_turn_end INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tool_execution_logs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL DEFAULT '{}',
                    output_json TEXT NOT NULL DEFAULT '{}',
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );
                """
            )

            if user_columns_before_create:
                self._ensure_column(
                    connection,
                    table_name="users",
                    column_name="phone",
                    column_definition="TEXT",
                )
            self._ensure_column(
                connection,
                table_name="sessions",
                column_name="user_id",
                column_definition="TEXT",
            )
            self._ensure_column(
                connection,
                table_name="messages",
                column_name="structured_content",
                column_definition="TEXT",
            )
            self._ensure_column(
                connection,
                table_name="messages",
                column_name="tool_calls_json",
                column_definition="TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                connection,
                table_name="session_memory",
                column_name="confidence",
                column_definition="REAL NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                table_name="session_memory",
                column_name="source_turn_start",
                column_definition="INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                table_name="session_memory",
                column_name="source_turn_end",
                column_definition="INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                table_name="session_memory",
                column_name="stable_profile_json",
                column_definition="TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                connection,
                table_name="session_memory",
                column_name="temporary_state_json",
                column_definition="TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                connection,
                table_name="session_memory",
                column_name="conflicts_json",
                column_definition="TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                connection,
                table_name="user_memory",
                column_name="user_profile_json",
                column_definition="TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                connection,
                table_name="user_memory",
                column_name="stable_profile_json",
                column_definition="TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                connection,
                table_name="user_memory",
                column_name="conflicts_json",
                column_definition="TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                connection,
                table_name="user_memory",
                column_name="confidence",
                column_definition="REAL NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                table_name="user_memory_candidates",
                column_name="session_id",
                column_definition="TEXT",
            )
            self._ensure_column(
                connection,
                table_name="user_memory_candidates",
                column_name="previous_value",
                column_definition="TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                connection,
                table_name="user_memory_candidates",
                column_name="scope",
                column_definition="TEXT NOT NULL DEFAULT 'user'",
            )
            self._ensure_column(
                connection,
                table_name="user_memory_candidates",
                column_name="source_type",
                column_definition="TEXT NOT NULL DEFAULT 'user'",
            )
            self._ensure_column(
                connection,
                table_name="user_memory_candidates",
                column_name="status",
                column_definition="TEXT NOT NULL DEFAULT 'pending_confirmation'",
            )
            self._ensure_column(
                connection,
                table_name="user_memory_candidates",
                column_name="reason",
                column_definition="TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                connection,
                table_name="user_memory_candidates",
                column_name="confidence",
                column_definition="REAL NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                table_name="user_memory_candidates",
                column_name="source_turn_start",
                column_definition="INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                table_name="user_memory_candidates",
                column_name="source_turn_end",
                column_definition="INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                table_name="user_memory_candidates",
                column_name="created_at",
                column_definition="TEXT",
            )
            self._ensure_column(
                connection,
                table_name="user_memory_candidates",
                column_name="updated_at",
                column_definition="TEXT",
            )

            now = datetime.now(UTC).isoformat()
            connection.execute(
                """
                INSERT INTO users (id, display_name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    display_name = excluded.display_name,
                    updated_at = excluded.updated_at
                """,
                (
                    settings.default_user_id,
                    settings.default_user_name,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE sessions
                SET user_id = ?
                WHERE user_id IS NULL OR TRIM(user_id) = ''
                """,
                (settings.default_user_id,),
            )

            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_session_created_at
                ON messages(session_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
                ON sessions(updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_sessions_user_updated_at
                ON sessions(user_id, updated_at DESC);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_unique
                ON users(phone)
                WHERE phone IS NOT NULL AND TRIM(phone) <> '';

                CREATE INDEX IF NOT EXISTS idx_auth_verification_codes_phone_purpose
                ON auth_verification_codes(phone, purpose, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_user_memory_candidates_user_status
                ON user_memory_candidates(user_id, status, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_tool_execution_logs_session_created_at
                ON tool_execution_logs(session_id, created_at DESC);
                """
            )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }

        if column_name in existing_columns:
            return

        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


database = Database(settings.sqlite_path)
