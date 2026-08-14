from __future__ import annotations

import json
import unittest

import httpx

from jira_autocompleter.llm import OpenAIService


def response_payload(data: dict) -> dict:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": json.dumps(data, ensure_ascii=False)}
                ],
            }
        ],
    }


class OpenAIServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_analysis_returns_up_to_five_questions(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            self.assertEqual(body["model"], "gpt-5.3-codex")
            self.assertEqual(body["text"]["format"]["type"], "json_schema")
            self.assertFalse(body["store"])
            return httpx.Response(
                200,
                json=response_payload(
                    {"questions": ["Для кого функция?", "Как проверить готовность?"], "final_task": ""}
                ),
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://api.openai.com"
        )
        service = OpenAIService("test-key", client=client)
        try:
            result = await service.analyze_task("nafanyah", "Добавить фильтр", "README")
        finally:
            await client.aclose()
        self.assertEqual(len(result.questions), 2)
        self.assertEqual(result.final_task, "")

    async def test_completion_returns_markdown(self) -> None:
        expected = "# Фильтр\n\n## Открытые вопросы\nНет"

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=response_payload({"final_task": expected}))

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://api.openai.com"
        )
        service = OpenAIService("test-key", client=client)
        try:
            result = await service.complete_task(
                "nafanyah", "Фильтр", ["Для кого?"], "Для менеджера", "README"
            )
        finally:
            await client.aclose()
        self.assertEqual(result, expected)

    async def test_compliment_is_extracted(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json=response_payload({"compliment": "Никита, ты великолепен!"})
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://api.openai.com"
        )
        service = OpenAIService("test-key", client=client)
        try:
            result = await service.generate_compliment("nafanyah")
        finally:
            await client.aclose()
        self.assertEqual(result, "Никита, ты великолепен!")
