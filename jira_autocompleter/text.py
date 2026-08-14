from __future__ import annotations


def split_telegram_message(text: str, limit: int = 3900) -> list[str]:
    """Split text into Telegram-safe chunks, preferring paragraph boundaries."""
    normalized = text.strip()
    if not normalized:
        return []
    if limit < 100:
        raise ValueError("limit must be at least 100 characters")

    chunks: list[str] = []
    remaining = normalized
    while len(remaining) > limit:
        boundary = remaining.rfind("\n\n", 0, limit + 1)
        if boundary < limit // 2:
            boundary = remaining.rfind("\n", 0, limit + 1)
        if boundary < limit // 2:
            boundary = remaining.rfind(" ", 0, limit + 1)
        if boundary < limit // 2:
            boundary = limit
        chunk = remaining[:boundary].rstrip()
        if not chunk:
            chunk = remaining[:limit]
            boundary = limit
        chunks.append(chunk)
        remaining = remaining[boundary:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
