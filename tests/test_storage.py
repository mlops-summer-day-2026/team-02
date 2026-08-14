from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jira_autocompleter.storage import Storage


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_settings_persist_and_draft_is_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory) / "bot.sqlite3")
            await storage.initialize(
                "@nafanyah", "https://github.com/mlops-summer-day-2026/team-02"
            )
            self.assertEqual(
                await storage.get_repository("NAFANYAH"),
                "https://github.com/mlops-summer-day-2026/team-02",
            )

            await storage.set_repository(
                "@nafanyah", "https://github.com/example/new-repo"
            )
            self.assertEqual(
                await storage.get_repository("nafanyah"),
                "https://github.com/example/new-repo",
            )

            await storage.save_draft(
                "nafanyah",
                "Короткая задача",
                "repo context",
                ["Вопрос один?", "Вопрос два?"],
            )
            draft = await storage.get_draft("@NAFANYAH")
            self.assertIsNotNone(draft)
            assert draft is not None
            self.assertEqual(draft.questions, ("Вопрос один?", "Вопрос два?"))

            await storage.delete_draft("nafanyah")
            self.assertIsNone(await storage.get_draft("nafanyah"))
