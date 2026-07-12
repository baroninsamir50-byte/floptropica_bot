from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from aiogram import Bot
from io import BytesIO
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionFactory
from app.models import InventoryItem, ItemTemplate, OwnedNpc
from app.miniapp.auth import TelegramMiniAppUser, current_miniapp_user
from app.services import (
    buy_item, claim_work, get_character, get_daily_shop_items,
    get_equipment_bonuses, get_system_media, local_date,
    start_work, toggle_equip, xp_for_next, claim_daily_reward,
    level_income_multiplier, level_rank,
)
from app.work_catalog import available_professions, profession_by_key, title_can_use

router = APIRouter(prefix="/api/miniapp", tags=["miniapp"])
_bot_username_cache: str | None = None

async def get_bot_username() -> str | None:
    global _bot_username_cache
    if _bot_username_cache:
        return _bot_username_cache
    from app.config import get_settings
    bot = Bot(get_settings().bot_token)
    try:
        me = await bot.get_me()
        _bot_username_cache = me.username
        return _bot_username_cache
    finally:
        await bot.session.close()


async def get_session():
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def require_character(user, session):
    c = await get_character(session, user.id)
    if not c:
        raise HTTPException(404, "Сначала создайте персонажа через /start")
    return c

class DevelopmentRequest(BaseModel):
    stat: Literal["health","mana","strength","intelligence","agility","magic","luck","endurance","charisma"]
    amount: Literal[1,5]
class ProfessionRequest(BaseModel):
    key: str = Field(min_length=1, max_length=40)
class ItemRequest(BaseModel):
    item_id: int
class InventoryRequest(BaseModel):
    inventory_id: int


async def telegram_file_response(file_id: str) -> Response:
    from app.config import get_settings
    bot = Bot(get_settings().bot_token)
    try:
        telegram_file = await bot.get_file(file_id)
        stream = BytesIO()
        await bot.download_file(telegram_file.file_path, destination=stream)
        return Response(
            content=stream.getvalue(),
            media_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=900"},
        )
    finally:
        await bot.session.close()


@router.get("/bootstrap")
async def bootstrap(user: TelegramMiniAppUser=Depends(current_miniapp_user), session: AsyncSession=Depends(get_session)):
    c = await require_character(user, session)
    bonuses = await get_equipment_bonuses(session, c.id)
    total = lambda k: int(getattr(c,k)) + int(bonuses.get(k,0))
    shop = await get_daily_shop_items(session, 5)
    inv_result = await session.execute(
        select(InventoryItem, ItemTemplate).join(ItemTemplate, ItemTemplate.id==InventoryItem.item_id)
        .where(InventoryItem.character_id==c.id).order_by(ItemTemplate.name)
    )
    inventory=[{
        "inventory_id":inv.id,"item_id":item.id,"name":item.name,"description":item.description,
        "quantity":inv.quantity,"equipped":inv.equipped,"slot":item.slot,"rarity":item.rarity,
        "stat_name":item.stat_name,"stat_bonus":item.stat_bonus,
    } for inv,item in inv_result.all()]
    npc_result=await session.execute(select(OwnedNpc).where(OwnedNpc.character_id==c.id))
    npcs={n.npc_type:n.quantity for n in npc_result.scalars()}
    media_keys=("home_bg","hero_bg","house_bg","treasury","shop","development","factions","map","games_bg","inventory_bg","loading_bg","app_logo","topbar_bg","nav_bg","card_texture","frame_hero","frame_house","icon_hero","icon_house","icon_treasury","icon_shop","icon_map","icon_games","icon_factions","icon_inventory","icon_development","icon_daily")
    media={k:(f"/api/miniapp/media/{k}" if await get_system_media(session,k) else None) for k in media_keys}
    remaining=0
    if c.work_ends_at and not c.work_reward_claimed:
        remaining=max(0,int((c.work_ends_at-datetime.now(timezone.utc)).total_seconds()))
    bot_username = await get_bot_username()
    return {
        "bot_username": bot_username,
        "hero":{"name":c.name,"level":c.level,"experience":c.experience,"experience_next":xp_for_next(c.level),
        "gold":c.gold,"profession":c.profession,"title":c.title,"faction":c.faction,"social_status":c.social_status,
        "reputation":c.reputation,"development_points":c.development_points,
        "portrait_available": bool(c.portrait_file_id),
        "rank":level_rank(c.level),"income_multiplier":round(level_income_multiplier(c.level),2),
        "login_streak":c.login_streak,"daily_reward_available":c.daily_reward_date != local_date(),
        "stats":{k:total(k) for k in ("health","mana","strength","intelligence","agility","magic","luck","endurance","charisma")}},
        "house":{"name":c.house.name if c.house else None,"location":c.house.location if c.house else None,
        "description":c.house.description if c.house else None,"level":c.house.level if c.house else None,
        "value":c.house.value if c.house else None,"defense":c.house.defense if c.house else None,
        "integrity":c.house.integrity if c.house else None,
        "repair_energy":c.house.repair_energy if c.house else None,
        "image_available": bool(c.house and c.house.image_file_id)},
        "work":{"count":c.work_count,"active":bool(c.work_ends_at and not c.work_reward_claimed),"remaining_seconds":remaining},
        "professions":[{"key":k,"name":str(d["name"]),"label":str(d["label"]),"gold":list(d["gold"]),"xp":list(d["xp"])}
            for k,d in available_professions(c.title)],
        "shop":{"date":local_date(),"items":[{"id":i.id,"name":i.name,"description":i.description,"price":i.price,
            "slot":i.slot,"rarity":i.rarity,"stat_name":i.stat_name,"stat_bonus":i.stat_bonus} for i in shop]},
        "inventory":inventory,"npcs":npcs,"media":media,
    }

@router.post("/development")
async def development(payload: DevelopmentRequest,user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    c=await require_character(user,session)
    if c.development_points<payload.amount: raise HTTPException(400,"Недостаточно очков развития")
    c.development_points-=payload.amount
    setattr(c,payload.stat,getattr(c,payload.stat)+payload.amount)
    return {"ok":True}

@router.post("/profession")
async def profession(payload: ProfessionRequest,user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    c=await require_character(user,session); data=profession_by_key(payload.key)
    if not data: raise HTTPException(404,"Профессия не найдена")
    if not title_can_use(c.title,data): raise HTTPException(403,"Профессия недоступна для вашей роли")
    c.profession=str(data["name"]); return {"ok":True,"profession":c.profession}

@router.post("/work/start")
async def work_start(user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    c=await require_character(user,session)
    try: return {"ok":True,"message":await start_work(c,c.profession)}
    except ValueError as e: raise HTTPException(400,str(e))

@router.post("/work/claim")
async def work_claim(user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    c=await require_character(user,session)
    try:
        gold,xp=await claim_work(session,c); return {"ok":True,"gold":gold,"xp":xp}
    except ValueError as e: raise HTTPException(400,str(e))

@router.post("/shop/buy")
async def shop_buy(payload:ItemRequest,user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    c=await require_character(user,session)
    try:
        item=await buy_item(session,c,payload.item_id); return {"ok":True,"item":item.name,"gold":c.gold}
    except ValueError as e: raise HTTPException(400,str(e))

@router.post("/inventory/equip")
async def inv_equip(payload:InventoryRequest,user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    c=await require_character(user,session)
    try:
        name,equipped=await toggle_equip(session,c,payload.inventory_id)
        return {"ok":True,"name":name,"equipped":equipped}
    except ValueError as e: raise HTTPException(400,str(e))



@router.post("/daily-reward")
async def daily_reward(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    c = await require_character(user, session)
    try:
        gold, xp, development = await claim_daily_reward(session, c)
        return {
            "ok": True,
            "gold": gold,
            "xp": xp,
            "development": development,
            "streak": c.login_streak,
        }
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/media/{key}")
async def miniapp_media(key: str):
    allowed = {
        "home_bg","hero_bg","house_bg","treasury","shop","development",
        "factions","map","games_bg","inventory_bg","loading_bg","app_logo",
        "topbar_bg","nav_bg","card_texture","frame_hero","frame_house",
        "icon_hero","icon_house","icon_treasury","icon_shop","icon_map",
        "icon_games","icon_factions","icon_inventory","icon_development",
        "icon_daily",
    }
    if key not in allowed:
        raise HTTPException(404, "Изображение не найдено")

    async with SessionFactory() as session:
        file_id = await get_system_media(session, key)
    if not file_id:
        raise HTTPException(404, "Изображение не загружено")

    return await telegram_file_response(file_id)



@router.get("/hero-image")
async def hero_image(
    user: TelegramMiniAppUser = Depends(current_miniapp_user),
    session: AsyncSession = Depends(get_session),
):
    character = await require_character(user, session)
    if not character.portrait_file_id:
        raise HTTPException(404, "Портрет персонажа не загружен")
    return await telegram_file_response(character.portrait_file_id)


@router.get("/house-image")
async def house_image(
    user: TelegramMiniAppUser = Depends(current_miniapp_user),
    session: AsyncSession = Depends(get_session),
):
    character = await require_character(user, session)
    if not character.house or not character.house.image_file_id:
        raise HTTPException(404, "Фотография дома не загружена")
    return await telegram_file_response(character.house.image_file_id)
