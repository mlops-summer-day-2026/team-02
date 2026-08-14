from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx


class TTSError(RuntimeError):
    """The local TeraTTS service could not produce Telegram voice audio."""


@dataclass(frozen=True)
class VoiceAudio:
    data: bytes
    filename: str


class TeraTTSService:
    """HTTP adapter for a local TeraTTS service.

    Expected contract:
      POST TERATTS_URL
      JSON: {"text": "...", "response_format": "ogg_opus"}
      Response: non-empty OGG/Opus bytes.
    """

    def __init__(
        self,
        url: str,
        timeout_seconds: float = 30,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.url = url
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def synthesize(self, text: str) -> VoiceAudio:
        try:
            response = await self.client.post(
                self.url,
                json={"text": text, "response_format": "telegram_voice"},
                headers={"Accept": "audio/ogg, audio/mp4, audio/mpeg"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TTSError(f"TeraTTS вернул HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise TTSError("Локальный сервис TeraTTS недоступен") from exc

        audio = response.content
        if not audio:
            raise TTSError("TeraTTS вернул пустой аудиофайл")
        if audio.startswith(b"OggS"):
            return VoiceAudio(audio, "nikita-compliment.ogg")
        if len(audio) >= 12 and audio[4:8] == b"ftyp":
            return VoiceAudio(audio, "nikita-compliment.m4a")
        if audio.startswith(b"ID3") or audio[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
            return VoiceAudio(audio, "nikita-compliment.mp3")
        raise TTSError("TeraTTS должен вернуть OGG/Opus, M4A или MP3")
