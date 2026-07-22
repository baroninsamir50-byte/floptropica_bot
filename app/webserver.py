import hmac

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.miniapp.api import router as miniapp_router

from app.config import get_settings
from app.scheduler import process_due_game_tasks

app = FastAPI(title="Floptropica Bot Health")

STATIC_DIR = Path(__file__).resolve().parent / "miniapp" / "static"
app.mount("/miniapp/static", StaticFiles(directory=STATIC_DIR), name="miniapp-static")
app.include_router(miniapp_router)

@app.get("/miniapp")
async def miniapp_index():
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


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


@app.get("/version")
async def version():
    return {"version":"7.7.7","work_shifts":6,"farm":True,"farm_price":0,"first_farmer_price":70,"farm_start_plots":3,"npc_hunger":True,"safe_rest":True,"estate_events":20,"event_cycle_days":3,"player_market":True,"work_reward_multiplier":1.5,"title_income_bonuses":True,"title_potions":True,"npc_progression":"1-50 with ascension at 20 and 30","player_stories":True,"secret_story_achievement":True,"summer_guard_until":"2026-08-25"}
