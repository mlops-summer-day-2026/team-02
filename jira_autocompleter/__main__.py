from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from .config import ConfigError, Settings
from .llm import OpenAIService
from .repository import RepositoryService
from .storage import Storage
from .telegram_app import AppServices, create_dispatcher
from .tts import TeraTTSService
from .whitelist import Whitelist


async def run() -> None:
    settings = Settings.from_env()
    storage = Storage(settings.database_path)
    await storage.initialize(
        settings.default_repository_user, settings.default_repository_url
    )
    llm = OpenAIService(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        reasoning_effort=settings.openai_reasoning_effort,
    )
    tts = TeraTTSService(
        url=settings.teratts_url,
        timeout_seconds=settings.teratts_timeout_seconds,
    )
    services = AppServices(
        whitelist=Whitelist(settings.whitelist_path),
        storage=storage,
        repositories=RepositoryService(
            settings.repositories_dir, settings.max_repository_bytes
        ),
        llm=llm,
        tts=tts,
    )
    dispatcher = create_dispatcher(services)
    bot = Bot(token=settings.telegram_bot_token)
    try:
        await dispatcher.start_polling(
            bot, allowed_updates=dispatcher.resolve_used_update_types()
        )
    finally:
        await bot.session.close()
        await llm.close()
        await tts.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run())
    except ConfigError as exc:
        raise SystemExit(f"Ошибка конфигурации: {exc}") from exc


if __name__ == "__main__":
    main()
