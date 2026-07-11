import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.config import get_settings
from app.database import init_database, SessionFactory
from app.middlewares import DatabaseMiddleware
from app.routers import admin, common, economy, gameplay, profile, registration
from app.services import seed_items


async def run_web_server() -> None:
    settings = get_settings()
    config = uvicorn.Config(
        "app.webserver:app",
        host="0.0.0.0",
        port=settings.port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_bot() -> None:
    settings = get_settings()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.update.middleware(DatabaseMiddleware())

    dp.include_router(registration.router)
    dp.include_router(profile.router)
    dp.include_router(gameplay.router)
    dp.include_router(economy.router)
    dp.include_router(admin.router)
    dp.include_router(common.router)

    await bot.delete_webhook(drop_pending_updates=False)
    await bot.set_my_commands([BotCommand(command="menu", description="Главное меню"), BotCommand(command="profile", description="Мой персонаж"), BotCommand(command="house", description="Мой дом"), BotCommand(command="shop", description="Магазин дня"), BotCommand(command="ping", description="Проверить бота"), BotCommand(command="help", description="Помощь")])
    await dp.start_polling(bot)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    await init_database()
    async with SessionFactory() as session:
        await seed_items(session)

    await asyncio.gather(
        run_web_server(),
        run_bot(),
    )


if __name__ == "__main__":
    asyncio.run(main())
