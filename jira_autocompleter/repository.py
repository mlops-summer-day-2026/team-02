from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .whitelist import normalize_username


class RepositoryError(RuntimeError):
    """A repository cannot be validated, updated, or read safely."""


class RepositoryTooLarge(RepositoryError):
    """The tracked textual repository content exceeds the configured MVP limit."""


@dataclass(frozen=True)
class RepositorySnapshot:
    url: str
    branch: str
    revision: str
    context: str
    file_count: int


class RepositoryService:
    _SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
    _DENIED_NAMES = {
        ".env",
        "credentials",
        "credentials.json",
        "id_rsa",
        "id_ed25519",
        "secret.md",
        "secrets.yml",
        "secrets.yaml",
    }
    _DENIED_SUFFIXES = {
        ".key",
        ".pem",
        ".p12",
        ".pfx",
        ".keystore",
        ".jks",
    }

    def __init__(self, repositories_dir: Path, max_bytes: int = 1_000_000) -> None:
        self.repositories_dir = repositories_dir
        self.max_bytes = max_bytes

    @classmethod
    def canonicalize_github_url(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
            raise RepositoryError("Поддерживаются только публичные HTTPS-ссылки GitHub")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2:
            raise RepositoryError("Ожидается ссылка вида https://github.com/owner/repository")
        owner, repository = parts
        if repository.endswith(".git"):
            repository = repository[:-4]
        if not owner or not repository:
            raise RepositoryError("В ссылке не указаны owner и repository")
        if not cls._SAFE_COMPONENT.fullmatch(owner) or not cls._SAFE_COMPONENT.fullmatch(
            repository
        ):
            raise RepositoryError("Недопустимые символы в GitHub-ссылке")
        return f"https://github.com/{owner}/{repository}"

    async def validate_public_repository(self, value: str) -> str:
        url = self.canonicalize_github_url(value)
        slug = url.removeprefix("https://github.com/")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"https://api.github.com/repos/{slug}",
                    headers={
                        "Accept": "application/vnd.github+json",
                        "User-Agent": "jira-autocompleter",
                    },
                )
                if response.status_code == 404:
                    raise RepositoryError("Публичный репозиторий не найден")
                response.raise_for_status()
                metadata = response.json()
        except RepositoryError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise RepositoryError("Не удалось проверить репозиторий через GitHub API") from exc
        if metadata.get("private") is not False:
            raise RepositoryError("Для MVP поддерживаются только публичные репозитории")
        await self._git("ls-remote", "--exit-code", f"{url}.git", "HEAD")
        return url

    async def snapshot(self, username: str, value: str) -> RepositorySnapshot:
        url = self.canonicalize_github_url(value)
        local_path = self._local_path(username, url)
        self.repositories_dir.mkdir(parents=True, exist_ok=True)

        if not (local_path / ".git").is_dir():
            if local_path.exists():
                raise RepositoryError(
                    f"Каталог кэша существует, но не является Git-репозиторием: {local_path}"
                )
            await self._git("clone", f"{url}.git", str(local_path))

        await self._git("-C", str(local_path), "fetch", "--prune", "origin")
        branch = await self._select_branch(local_path)
        await self._git(
            "-C",
            str(local_path),
            "checkout",
            "--detach",
            f"origin/{branch}",
        )
        revision = (
            await self._git("-C", str(local_path), "rev-parse", "HEAD")
        ).strip()
        context, file_count = await asyncio.to_thread(self._read_context, local_path)
        return RepositorySnapshot(url, branch, revision, context, file_count)

    def _local_path(self, username: str, url: str) -> Path:
        owner, repository = url.removeprefix("https://github.com/").split("/", 1)
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
        user = normalize_username(username) or "unknown"
        slug = f"{user}-{owner}-{repository}-{digest}"
        return self.repositories_dir / slug

    async def _select_branch(self, local_path: Path) -> str:
        dev = await self._git(
            "-C",
            str(local_path),
            "rev-parse",
            "--verify",
            "--quiet",
            "refs/remotes/origin/dev",
            check=False,
        )
        if dev.strip():
            return "dev"

        default_ref = await self._git(
            "-C", str(local_path), "symbolic-ref", "refs/remotes/origin/HEAD"
        )
        prefix = "refs/remotes/origin/"
        branch = default_ref.strip()
        if not branch.startswith(prefix):
            raise RepositoryError("Не удалось определить default branch репозитория")
        return branch[len(prefix) :]

    def _read_context(self, local_path: Path) -> tuple[str, int]:
        import subprocess

        completed = subprocess.run(
            ["git", "-C", str(local_path), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
        relative_paths = [
            Path(item.decode("utf-8"))
            for item in completed.stdout.split(b"\0")
            if item
        ]
        chunks: list[str] = []
        total_bytes = 0
        file_count = 0

        for relative_path in sorted(relative_paths):
            if self._is_denied(relative_path):
                continue
            absolute_path = (local_path / relative_path).resolve()
            try:
                absolute_path.relative_to(local_path.resolve())
            except ValueError as exc:
                raise RepositoryError("Файл вышел за пределы репозитория") from exc
            raw = absolute_path.read_bytes()
            if b"\0" in raw:
                continue
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            projected = total_bytes + len(raw)
            if projected > self.max_bytes:
                raise RepositoryTooLarge(
                    "Текстовый контекст репозитория превышает лимит "
                    f"{self.max_bytes} байт"
                )
            chunks.append(f"===== {relative_path.as_posix()} =====\n{content}")
            total_bytes = projected
            file_count += 1

        return "\n\n".join(chunks), file_count

    @classmethod
    def _is_denied(cls, path: Path) -> bool:
        name = path.name.lower()
        if name in cls._DENIED_NAMES:
            return True
        if name.startswith(".env") and name != ".env.example":
            return True
        return path.suffix.lower() in cls._DENIED_SUFFIXES

    @staticmethod
    async def _git(*args: str, check: bool = True) -> str:
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode("utf-8", errors="replace")
        if check and process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise RepositoryError(detail or "Git завершился с ошибкой")
        return output
