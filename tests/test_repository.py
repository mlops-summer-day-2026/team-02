from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from jira_autocompleter.repository import (
    RepositoryError,
    RepositoryService,
    RepositoryTooLarge,
)


class RepositoryTests(unittest.TestCase):
    def test_canonicalizes_public_github_url(self) -> None:
        self.assertEqual(
            RepositoryService.canonicalize_github_url(
                "https://github.com/mlops-summer-day-2026/team-02.git"
            ),
            "https://github.com/mlops-summer-day-2026/team-02",
        )

    def test_rejects_non_github_and_nested_urls(self) -> None:
        invalid = [
            "http://github.com/owner/repo",
            "https://gitlab.com/owner/repo",
            "https://github.com/owner",
            "https://github.com/owner/repo/issues",
        ]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(RepositoryError):
                RepositoryService.canonicalize_github_url(url)

    def test_reads_tracked_text_and_skips_secrets_and_binary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            (root / ".env.example").write_text("TOKEN=\n", encoding="utf-8")
            (root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
            (root / "image.bin").write_bytes(b"abc\x00def")
            subprocess.run(
                ["git", "-C", str(root), "add", "app.py", ".env.example", "image.bin"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "add", "-f", ".env"],
                check=True,
                capture_output=True,
            )
            service = RepositoryService(root / "cache", max_bytes=10_000)
            context, file_count = service._read_context(root)
            self.assertIn("app.py", context)
            self.assertIn(".env.example", context)
            self.assertNotIn("TOKEN=secret", context)
            self.assertNotIn("image.bin", context)
            self.assertEqual(file_count, 2)

    def test_repository_size_limit_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            (root / "large.txt").write_text("x" * 101, encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", "large.txt"],
                check=True,
                capture_output=True,
            )
            service = RepositoryService(root / "cache", max_bytes=100)
            with self.assertRaises(RepositoryTooLarge):
                service._read_context(root)
