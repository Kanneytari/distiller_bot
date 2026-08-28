import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import get_settings
from .database import create_engine, create_session_factory, init_database
from .handlers import router


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    settings = get_settings()
    engine = create_engine(settings)
    await init_database(engine)
    session_factory = create_session_factory(engine)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    try:
        await dispatcher.start_polling(bot, session_factory=session_factory)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
