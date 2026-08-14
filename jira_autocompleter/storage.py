from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .whitelist import normalize_username


@dataclass(frozen=True)
class Draft:
    username: str
    original_request: str
    repository_context: str
    questions: tuple[str, ...]


class Storage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path), timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    async def initialize(self, default_user: str, default_repository_url: str) -> None:
        await asyncio.to_thread(
            self._initialize_sync, default_user, default_repository_url
        )

    def _initialize_sync(self, default_user: str, default_repository_url: str) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                    username TEXT PRIMARY KEY,
                    repository_url TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS drafts (
                    username TEXT PRIMARY KEY,
                    original_request TEXT NOT NULL,
                    repository_context TEXT NOT NULL,
                    questions_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            username = normalize_username(default_user)
            if username and default_repository_url:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO user_settings (username, repository_url)
                    VALUES (?, ?)
                    """,
                    (username, default_repository_url),
                )

    async def get_repository(self, username: str) -> Optional[str]:
        return await asyncio.to_thread(self._get_repository_sync, username)

    def _get_repository_sync(self, username: str) -> Optional[str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT repository_url FROM user_settings WHERE username = ?",
                (normalize_username(username),),
            ).fetchone()
        return str(row["repository_url"]) if row else None

    async def set_repository(self, username: str, repository_url: str) -> None:
        await asyncio.to_thread(self._set_repository_sync, username, repository_url)

    def _set_repository_sync(self, username: str, repository_url: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_settings (username, repository_url, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(username) DO UPDATE SET
                    repository_url = excluded.repository_url,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (normalize_username(username), repository_url),
            )

    async def save_draft(
        self,
        username: str,
        original_request: str,
        repository_context: str,
        questions: Sequence[str],
    ) -> None:
        await asyncio.to_thread(
            self._save_draft_sync,
            username,
            original_request,
            repository_context,
            tuple(questions),
        )

    def _save_draft_sync(
        self,
        username: str,
        original_request: str,
        repository_context: str,
        questions: tuple[str, ...],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO drafts (
                    username, original_request, repository_context, questions_json, created_at
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(username) DO UPDATE SET
                    original_request = excluded.original_request,
                    repository_context = excluded.repository_context,
                    questions_json = excluded.questions_json,
                    created_at = CURRENT_TIMESTAMP
                """,
                (
                    normalize_username(username),
                    original_request,
                    repository_context,
                    json.dumps(questions, ensure_ascii=False),
                ),
            )

    async def get_draft(self, username: str) -> Optional[Draft]:
        return await asyncio.to_thread(self._get_draft_sync, username)

    def _get_draft_sync(self, username: str) -> Optional[Draft]:
        normalized = normalize_username(username)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT original_request, repository_context, questions_json
                FROM drafts WHERE username = ?
                """,
                (normalized,),
            ).fetchone()
        if not row:
            return None
        questions = tuple(json.loads(str(row["questions_json"])))
        return Draft(
            username=normalized,
            original_request=str(row["original_request"]),
            repository_context=str(row["repository_context"]),
            questions=questions,
        )

    async def delete_draft(self, username: str) -> None:
        await asyncio.to_thread(self._delete_draft_sync, username)

    def _delete_draft_sync(self, username: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM drafts WHERE username = ?",
                (normalize_username(username),),
            )
