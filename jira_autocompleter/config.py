from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when a required application setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    openai_api_key: str
    openai_model: str
    openai_reasoning_effort: str
    teratts_url: str
    teratts_timeout_seconds: float
    database_path: Path
    repositories_dir: Path
    whitelist_path: Path
    default_repository_user: str
    default_repository_url: str
    max_repository_bytes: int

    @classmethod
    def from_env(cls, project_root: Optional[Path] = None) -> "Settings":
        root = (project_root or Path(__file__).resolve().parent.parent).resolve()
        load_dotenv(root / ".env")

        def required(name: str) -> str:
            value = os.getenv(name, "").strip()
            if not value:
                raise ConfigError(f"Не задана обязательная переменная {name}")
            return value

        def local_path(name: str, default: str) -> Path:
            value = Path(os.getenv(name, default).strip()).expanduser()
            return value if value.is_absolute() else (root / value).resolve()

        try:
            tts_timeout = float(os.getenv("TERATTS_TIMEOUT_SECONDS", "30"))
            max_repository_bytes = int(os.getenv("MAX_REPOSITORY_BYTES", "1000000"))
        except ValueError as exc:
            raise ConfigError("Числовая переменная окружения имеет неверный формат") from exc

        if tts_timeout <= 0:
            raise ConfigError("TERATTS_TIMEOUT_SECONDS должна быть больше нуля")
        if max_repository_bytes <= 0:
            raise ConfigError("MAX_REPOSITORY_BYTES должна быть больше нуля")

        reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT", "medium").strip().lower()
        if reasoning_effort not in {"low", "medium", "high", "xhigh"}:
            raise ConfigError("OPENAI_REASONING_EFFORT: допустимы low, medium, high, xhigh")

        return cls(
            telegram_bot_token=required("TELEGRAM_BOT_TOKEN"),
            openai_api_key=required("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.3-codex").strip(),
            openai_reasoning_effort=reasoning_effort,
            teratts_url=os.getenv(
                "TERATTS_URL", "http://127.0.0.1:8001/synthesize"
            ).strip(),
            teratts_timeout_seconds=tts_timeout,
            database_path=local_path("DATABASE_PATH", "./data/bot.sqlite3"),
            repositories_dir=local_path("REPOSITORIES_DIR", "./data/repositories"),
            whitelist_path=local_path("WHITELIST_PATH", "./whitelist.txt"),
            default_repository_user=os.getenv(
                "DEFAULT_REPOSITORY_USER", "@nafanyah"
            ).strip(),
            default_repository_url=os.getenv(
                "DEFAULT_REPOSITORY_URL",
                "https://github.com/mlops-summer-day-2026/team-02",
            ).strip(),
            max_repository_bytes=max_repository_bytes,
        )
