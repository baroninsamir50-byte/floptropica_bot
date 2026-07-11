import hmac

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI, HTTPException, Query

from app.config import get_settings
from app.scheduler import process_due_game_tasks

app = FastAPI(title="Floptropica Bot Health")


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "floptropica-bot"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/tasks/run")
async def run_tasks(key: str = Query(default="")) -> dict[str, str]:
    """
    Защищённая точка для внешнего планировщика.

    Пример:
    https://YOUR-SERVICE.onrender.com/tasks/run?key=YOUR_CRON_SECRET
    """
    settings = get_settings()
    if not settings.cron_secret:
        raise HTTPException(
            status_code=503,
            detail="CRON_SECRET is not configured",
        )
    if not hmac.compare_digest(key, settings.cron_secret):
        raise HTTPException(status_code=403, detail="Invalid key")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        return await process_due_game_tasks(bot)
    finally:
        await bot.session.close()
