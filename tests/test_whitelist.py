from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jira_autocompleter.whitelist import Whitelist, normalize_username


class WhitelistTests(unittest.TestCase):
    def test_normalize_username(self) -> None:
        self.assertEqual(normalize_username(" @NaFaNyAh "), "nafanyah")
        self.assertEqual(normalize_username(None), "")

    def test_whitelist_ignores_comments_and_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "whitelist.txt"
            path.write_text("# team\n@NaFaNyAh\n\n@Other # comment\n", encoding="utf-8")
            whitelist = Whitelist(path)
            self.assertTrue(whitelist.is_allowed("nafanyah"))
            self.assertTrue(whitelist.is_allowed("OTHER"))
            self.assertFalse(whitelist.is_allowed("stranger"))
            self.assertFalse(whitelist.is_allowed(None))

    def test_whitelist_is_reloaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "whitelist.txt"
            path.write_text("@first\n", encoding="utf-8")
            whitelist = Whitelist(path)
            self.assertTrue(whitelist.is_allowed("first"))
            path.write_text("@second\n", encoding="utf-8")
            self.assertFalse(whitelist.is_allowed("first"))
            self.assertTrue(whitelist.is_allowed("second"))
