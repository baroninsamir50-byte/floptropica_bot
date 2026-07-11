import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats

from app.config import get_settings
from app.database import init_database, SessionFactory
from app.middlewares import DatabaseMiddleware
from app.routers import admin, common, economy, gameplay, games, house_defense, profile, registration
from app.services import seed_items
from app.scheduler import house_attack_loop, process_due_game_tasks


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
    dp.include_router(games.router)
    dp.include_router(house_defense.router)
    dp.include_router(admin.router)
    dp.include_router(common.router)

    await bot.delete_webhook(drop_pending_updates=False)
    private_commands = [
        BotCommand(command="start", description="Создать персонажа"),
        BotCommand(command="menu", description="Главное меню"),
        BotCommand(command="profile", description="Карточка героя"),
        BotCommand(command="house", description="Моё владение"),
        BotCommand(command="map", description="Карта Королевства"),
        BotCommand(command="shop", description="Магазин дня"),
        BotCommand(command="work", description="Начать работу"),
        BotCommand(command="work_status", description="Получить награду"),
        BotCommand(command="games", description="Игровая арена"),
        BotCommand(command="duel", description="Вызвать на дуэль"),
        BotCommand(command="expedition", description="Экспедиция до 6 игроков"),
        BotCommand(command="admin", description="Панель создателя"),
        BotCommand(command="help", description="Помощь"),
    ]
    group_commands = [
        BotCommand(command="menu", description="Главное меню"),
        BotCommand(command="profile", description="Мой герой"),
        BotCommand(command="house", description="Мой дом"),
        BotCommand(command="map", description="Карта Королевства"),
        BotCommand(command="games", description="Игровая арена"),
        BotCommand(command="duel", description="Дуэль с игроком"),
        BotCommand(command="expedition", description="Экспедиция до 6 игроков"),
        BotCommand(command="shop", description="Магазин дня"),
        BotCommand(command="ping", description="Проверить бота"),
        BotCommand(command="help", description="Помощь"),
    ]
    await bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())

    try:
        await process_due_game_tasks(bot)
    except Exception:
        logging.exception("Failed to process overdue game tasks on startup")

    scheduler_task = asyncio.create_task(house_attack_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()


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
