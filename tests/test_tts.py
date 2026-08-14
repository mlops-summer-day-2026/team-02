from __future__ import annotations

import unittest

import httpx

from jira_autocompleter.tts import TTSError, TeraTTSService


class TeraTTSServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_ogg_audio(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/synthesize")
            return httpx.Response(200, content=b"OggS-audio")

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://localhost"
        )
        service = TeraTTSService("http://localhost/synthesize", client=client)
        try:
            audio = await service.synthesize("Комплимент")
        finally:
            await client.aclose()
        self.assertEqual(audio.data, b"OggS-audio")
        self.assertEqual(audio.filename, "nikita-compliment.ogg")

    async def test_returns_m4a_audio(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"\x00\x00\x00\x18ftypM4A audio")

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://localhost"
        )
        service = TeraTTSService("http://localhost/synthesize", client=client)
        try:
            audio = await service.synthesize("Комплимент")
        finally:
            await client.aclose()
        self.assertEqual(audio.filename, "nikita-compliment.m4a")

    async def test_rejects_non_ogg_audio(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"RIFF-wav")

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://localhost"
        )
        service = TeraTTSService("http://localhost/synthesize", client=client)
        try:
            with self.assertRaises(TTSError):
                await service.synthesize("Комплимент")
        finally:
            await client.aclose()
