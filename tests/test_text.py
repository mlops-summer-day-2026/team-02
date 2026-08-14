from __future__ import annotations

import unittest

from jira_autocompleter.text import split_telegram_message


class TextTests(unittest.TestCase):
    def test_short_message_is_unchanged(self) -> None:
        self.assertEqual(split_telegram_message("Коротко"), ["Коротко"])

    def test_long_message_is_split_within_limit(self) -> None:
        text = "\n\n".join(["Раздел " + ("x" * 90) for _ in range(8)])
        chunks = split_telegram_message(text, limit=220)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 220 for chunk in chunks))
        self.assertEqual(" ".join(" ".join(chunks).split()), " ".join(text.split()))

    def test_empty_message_returns_no_chunks(self) -> None:
        self.assertEqual(split_telegram_message("  \n"), [])
