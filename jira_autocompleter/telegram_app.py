from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict

from aiogram import Bot, Dispatcher, F, Router
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.enums import ChatAction, ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, Message, TelegramObject

from .llm import LLMError, OpenAIService
from .repository import RepositoryError, RepositoryService
from .storage import Storage
from .text import split_telegram_message
from .tts import TTSError, TeraTTSService
from .whitelist import Whitelist, normalize_username

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppServices:
    whitelist: Whitelist
    storage: Storage
    repositories: RepositoryService
    llm: OpenAIService
    tts: TeraTTSService


class AccessMiddleware(BaseMiddleware):
    def __init__(self, whitelist: Whitelist) -> None:
        self.whitelist = whitelist

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        if event.chat.type != ChatType.PRIVATE:
            await event.answer("Jira Autocompleter работает только в личном чате")
            return None
        username = event.from_user.username if event.from_user else None
        if not self.whitelist.is_allowed(username):
            await event.answer("Доступ запрещён")
            return None
        data["username"] = normalize_username(username)
        return await handler(event, data)


def create_dispatcher(services: AppServices) -> Dispatcher:
    router = Router(name="jira-autocompleter")
    router.message.outer_middleware(AccessMiddleware(services.whitelist))

    @router.message(CommandStart())
    async def start(message: Message, username: str) -> None:
        repository_url = await services.storage.get_repository(username)
        repository_line = (
            f"Текущий репозиторий: {repository_url}"
            if repository_url
            else "Репозиторий ещё не настроен."
        )
        await message.answer(
            "Jira Autocompleter превращает короткое описание в подробную задачу.\n\n"
            f"{repository_line}\n\n"
            "Настройка: /repo https://github.com/owner/repository\n"
            "Отмена текущего черновика: /cancel"
        )

    @router.message(Command("repo"))
    async def set_repository(message: Message, username: str) -> None:
        text = message.text or ""
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            await message.answer(
                "Использование: /repo https://github.com/owner/repository"
            )
            return
        status = await message.answer("Проверяю публичный GitHub-репозиторий…")
        try:
            repository_url = await services.repositories.validate_public_repository(
                parts[1]
            )
            await services.storage.set_repository(username, repository_url)
            await services.storage.delete_draft(username)
        except RepositoryError as exc:
            await status.edit_text(f"Не удалось подключить репозиторий: {exc}")
            return
        await status.edit_text(
            f"Репозиторий сохранён: {repository_url}\n"
            "Перед каждой задачей обновлю ветку dev или default branch, если dev нет."
        )

    @router.message(Command("cancel"))
    async def cancel(message: Message, username: str) -> None:
        await services.storage.delete_draft(username)
        await message.answer("Черновик сброшен. Можно отправить новую задачу.")

    @router.message(F.text.startswith("/"))
    async def unknown_command(message: Message) -> None:
        await message.answer("Неизвестная команда. Доступны /start, /repo и /cancel.")

    @router.message(F.text)
    async def text_message(message: Message, username: str, bot: Bot) -> None:
        text = (message.text or "").strip()
        if not text:
            return
        if text.casefold() == "никита":
            await _send_compliment(message, username, bot, services)
            return

        draft = await services.storage.get_draft(username)
        if draft:
            await _finish_draft(message, username, text, bot, services)
            return

        repository_url = await services.storage.get_repository(username)
        if not repository_url:
            await message.answer(
                "Сначала укажите публичный репозиторий: "
                "/repo https://github.com/owner/repository"
            )
            return
        await _start_task(message, username, text, repository_url, bot, services)

    @router.message()
    async def unsupported_message(message: Message) -> None:
        await message.answer("Для MVP отправьте описание задачи обычным текстом.")

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def _start_task(
    message: Message,
    username: str,
    request: str,
    repository_url: str,
    bot: Bot,
    services: AppServices,
) -> None:
    status = await message.answer(
        f"Обновляю {repository_url} и читаю исходный код…"
    )
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        snapshot = await services.repositories.snapshot(username, repository_url)
        await status.edit_text(
            f"Анализирую {snapshot.file_count} файлов из ветки {snapshot.branch}…"
        )
        analysis = await services.llm.analyze_task(
            username, request, snapshot.context
        )
    except RepositoryError as exc:
        logger.warning("Repository processing failed for %s: %s", username, exc)
        await status.edit_text(f"Не удалось прочитать репозиторий: {exc}")
        return
    except LLMError as exc:
        logger.warning("OpenAI request failed for %s: %s", username, exc)
        await status.edit_text(f"Не удалось обработать задачу: {exc}")
        return

    if analysis.questions:
        await services.storage.save_draft(
            username,
            original_request=request,
            repository_context=snapshot.context,
            questions=analysis.questions,
        )
        question_text = "\n".join(
            f"{index}. {question}"
            for index, question in enumerate(analysis.questions, start=1)
        )
        await status.edit_text(
            "Ответьте на вопросы одним сообщением:\n\n" + question_text
        )
        return

    await status.edit_text("Готово.")
    await _send_long_message(message, analysis.final_task)


async def _finish_draft(
    message: Message,
    username: str,
    answer: str,
    bot: Bot,
    services: AppServices,
) -> None:
    draft = await services.storage.get_draft(username)
    if not draft:
        return
    status = await message.answer("Формирую итоговую постановку…")
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        final_task = await services.llm.complete_task(
            username=username,
            original_request=draft.original_request,
            questions=draft.questions,
            answer=answer,
            repository_context=draft.repository_context,
        )
    except LLMError as exc:
        logger.warning("OpenAI completion failed for %s: %s", username, exc)
        await status.edit_text(
            f"Не удалось сформировать задачу: {exc}\n"
            "Черновик сохранён — отправьте ответ ещё раз или используйте /cancel."
        )
        return

    await services.storage.delete_draft(username)
    await status.edit_text("Готово.")
    await _send_long_message(message, final_task)


async def _send_compliment(
    message: Message,
    username: str,
    bot: Bot,
    services: AppServices,
) -> None:
    await bot.send_chat_action(message.chat.id, ChatAction.RECORD_VOICE)
    try:
        compliment = await services.llm.generate_compliment(username)
        audio = await services.tts.synthesize(compliment)
    except (LLMError, TTSError) as exc:
        logger.warning("Compliment generation failed for %s: %s", username, exc)
        await message.answer(f"Не удалось создать голосовой комплимент: {exc}")
        return
    voice = BufferedInputFile(audio.data, filename=audio.filename)
    await message.answer_voice(voice=voice)


async def _send_long_message(message: Message, text: str) -> None:
    chunks = split_telegram_message(text)
    if not chunks:
        await message.answer("Codex вернул пустой результат.")
        return
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        prefix = f"[{index}/{total}]\n" if total > 1 else ""
        await message.answer(prefix + chunk)
