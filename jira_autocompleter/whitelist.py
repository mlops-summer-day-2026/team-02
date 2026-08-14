from __future__ import annotations

from pathlib import Path
from typing import Optional


def normalize_username(username: Optional[str]) -> str:
    if not username:
        return ""
    return username.strip().lower().lstrip("@")


class Whitelist:
    """File-backed allowlist reloaded on every check for zero-downtime edits."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def usernames(self) -> set[str]:
        if not self.path.exists():
            return set()
        allowed: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            value = line.split("#", 1)[0].strip()
            normalized = normalize_username(value)
            if normalized:
                allowed.add(normalized)
        return allowed

    def is_allowed(self, username: Optional[str]) -> bool:
        normalized = normalize_username(username)
        return bool(normalized) and normalized in self.usernames()
