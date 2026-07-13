from random import randint, choice
from datetime import datetime, timezone, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from aiogram import Bot
from aiogram.types import BufferedInputFile
from io import BytesIO
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionFactory
from app.models import (
    InventoryItem, ItemTemplate, OwnedNpc, Duel, Character, User,
    SystemMedia, TarotCard, TarotReading, House, HouseAttack, HouseRoom, NpcUnit,
)
from app.miniapp.auth import TelegramMiniAppUser, current_miniapp_user
from app.services import (
    buy_item, claim_work, get_character, get_daily_shop_items,
    get_equipment_bonuses, get_system_media, local_date,
    start_work, toggle_equip, xp_for_next, claim_daily_reward,
    level_income_multiplier, level_rank, set_system_media, change_gold, apply_levels,
    get_effective_stats,
)
from app.work_catalog import available_professions, profession_by_key, title_can_use
from app.miniapp.duel_engine import STYLES, initialize_duel, perform_action, log_list
from app.tarot_service import create_daily_reading, offered_cards

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
class DuelChallengeRequest(BaseModel):
    opponent_id: int
    style: str = "guardian"

class DuelAcceptRequest(BaseModel):
    style: str = "guardian"

class DuelActionRequest(BaseModel):
    action: Literal["attack","magic","defend","dodge","critical","potion"]


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
    media_keys=("home_bg","hero_bg","house_bg","treasury","shop","development","factions","map","games_bg","inventory_bg","loading_bg","app_logo","topbar_bg","nav_bg","card_texture","frame_hero","frame_house","icon_hero","icon_house","icon_treasury","icon_shop","icon_map","icon_games","icon_factions","icon_inventory","icon_development","icon_daily","duel_bg","duel_frame","duel_vs","icon_customization","tarot_bg","tarot_back","icon_tarot","npc_bg","icon_npc","room_bg","enemy_dragon_1","enemy_dragon_2","enemy_dragon_3","enemy_monster_1","enemy_monster_2","enemy_monster_3","enemy_anomaly_1","enemy_anomaly_2","enemy_anomaly_3","guard_model_1","guard_model_2","guard_model_3","peasant_model_1","peasant_model_2","peasant_model_3","npc_peasant_1","npc_peasant_2","npc_peasant_3","npc_farmer_1","npc_farmer_2","npc_farmer_3","npc_gardener_1","npc_gardener_2","npc_gardener_3","npc_forester_1","npc_forester_2","npc_forester_3","npc_miner_1","npc_miner_2","npc_miner_3","npc_fisher_1","npc_fisher_2","npc_fisher_3","npc_cook_1","npc_cook_2","npc_cook_3","npc_recruit_1","npc_recruit_2","npc_recruit_3","npc_guard_1","npc_guard_2","npc_guard_3","npc_veteran_1","npc_veteran_2","npc_veteran_3","npc_archer_1","npc_archer_2","npc_archer_3","npc_rider_1","npc_rider_2","npc_rider_3","npc_paladin_1","npc_paladin_2","npc_paladin_3","npc_dragon_tamer_1","npc_dragon_tamer_2","npc_dragon_tamer_3","npc_mage_1","npc_mage_2","npc_mage_3","npc_seer_1","npc_seer_2","npc_seer_3","npc_alchemist_1","npc_alchemist_2","npc_alchemist_3","npc_exorcist_1","npc_exorcist_2","npc_exorcist_3","npc_archmage_1","npc_archmage_2","npc_archmage_3","npc_merchant_1","npc_merchant_2","npc_merchant_3","npc_banker_1","npc_banker_2","npc_banker_3","npc_quartermaster_1","npc_quartermaster_2","npc_quartermaster_3","npc_treasurer_1","npc_treasurer_2","npc_treasurer_3","npc_judge_1","npc_judge_2","npc_judge_3","npc_scribe_1","npc_scribe_2","npc_scribe_3","npc_advisor_1","npc_advisor_2","npc_advisor_3","npc_chancellor_1","npc_chancellor_2","npc_chancellor_3","npc_bard_1","npc_bard_2","npc_bard_3","npc_artist_1","npc_artist_2","npc_artist_3","npc_librarian_1","npc_librarian_2","npc_librarian_3","npc_architect_1","npc_architect_2","npc_architect_3","npc_dog_1","npc_dog_2","npc_dog_3","npc_cat_1","npc_cat_2","npc_cat_3","npc_falcon_1","npc_falcon_2","npc_falcon_3","npc_small_dragon_1","npc_small_dragon_2","npc_small_dragon_3","npc_royal_architect_1","npc_royal_architect_2","npc_royal_architect_3","npc_great_magister_1","npc_great_magister_2","npc_great_magister_3","npc_royal_general_1","npc_royal_general_2","npc_royal_general_3","npc_forest_keeper_1","npc_forest_keeper_2","npc_forest_keeper_3","npc_angel_of_light_1","npc_angel_of_light_2","npc_angel_of_light_3")
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
        "is_admin": user.id in __import__("app.config", fromlist=["get_settings"]).get_settings().admins,
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
        "icon_daily","duel_bg","duel_frame","duel_vs","icon_customization",
        "tarot_bg","tarot_back","icon_tarot","npc_bg","icon_npc","room_bg",
        "enemy_dragon_1","enemy_dragon_2","enemy_dragon_3",
        "enemy_monster_1","enemy_monster_2","enemy_monster_3",
        "enemy_anomaly_1","enemy_anomaly_2","enemy_anomaly_3",
        "guard_model_1","guard_model_2","guard_model_3",
        "peasant_model_1","peasant_model_2","peasant_model_3",
        "npc_peasant_1",
        "npc_peasant_2",
        "npc_peasant_3",
        "npc_farmer_1",
        "npc_farmer_2",
        "npc_farmer_3",
        "npc_gardener_1",
        "npc_gardener_2",
        "npc_gardener_3",
        "npc_forester_1",
        "npc_forester_2",
        "npc_forester_3",
        "npc_miner_1",
        "npc_miner_2",
        "npc_miner_3",
        "npc_fisher_1",
        "npc_fisher_2",
        "npc_fisher_3",
        "npc_cook_1",
        "npc_cook_2",
        "npc_cook_3",
        "npc_recruit_1",
        "npc_recruit_2",
        "npc_recruit_3",
        "npc_guard_1",
        "npc_guard_2",
        "npc_guard_3",
        "npc_veteran_1",
        "npc_veteran_2",
        "npc_veteran_3",
        "npc_archer_1",
        "npc_archer_2",
        "npc_archer_3",
        "npc_rider_1",
        "npc_rider_2",
        "npc_rider_3",
        "npc_paladin_1",
        "npc_paladin_2",
        "npc_paladin_3",
        "npc_dragon_tamer_1",
        "npc_dragon_tamer_2",
        "npc_dragon_tamer_3",
        "npc_mage_1",
        "npc_mage_2",
        "npc_mage_3",
        "npc_seer_1",
        "npc_seer_2",
        "npc_seer_3",
        "npc_alchemist_1",
        "npc_alchemist_2",
        "npc_alchemist_3",
        "npc_exorcist_1",
        "npc_exorcist_2",
        "npc_exorcist_3",
        "npc_archmage_1",
        "npc_archmage_2",
        "npc_archmage_3",
        "npc_merchant_1",
        "npc_merchant_2",
        "npc_merchant_3",
        "npc_banker_1",
        "npc_banker_2",
        "npc_banker_3",
        "npc_quartermaster_1",
        "npc_quartermaster_2",
        "npc_quartermaster_3",
        "npc_treasurer_1",
        "npc_treasurer_2",
        "npc_treasurer_3",
        "npc_judge_1",
        "npc_judge_2",
        "npc_judge_3",
        "npc_scribe_1",
        "npc_scribe_2",
        "npc_scribe_3",
        "npc_advisor_1",
        "npc_advisor_2",
        "npc_advisor_3",
        "npc_chancellor_1",
        "npc_chancellor_2",
        "npc_chancellor_3",
        "npc_bard_1",
        "npc_bard_2",
        "npc_bard_3",
        "npc_artist_1",
        "npc_artist_2",
        "npc_artist_3",
        "npc_librarian_1",
        "npc_librarian_2",
        "npc_librarian_3",
        "npc_architect_1",
        "npc_architect_2",
        "npc_architect_3",
        "npc_dog_1",
        "npc_dog_2",
        "npc_dog_3",
        "npc_cat_1",
        "npc_cat_2",
        "npc_cat_3",
        "npc_falcon_1",
        "npc_falcon_2",
        "npc_falcon_3",
        "npc_small_dragon_1",
        "npc_small_dragon_2",
        "npc_small_dragon_3",
        "npc_royal_architect_1",
        "npc_royal_architect_2",
        "npc_royal_architect_3",
        "npc_great_magister_1",
        "npc_great_magister_2",
        "npc_great_magister_3",
        "npc_royal_general_1",
        "npc_royal_general_2",
        "npc_royal_general_3",
        "npc_forest_keeper_1",
        "npc_forest_keeper_2",
        "npc_forest_keeper_3",
        "npc_angel_of_light_1",
        "npc_angel_of_light_2",
        "npc_angel_of_light_3"
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


THEME_KEYS = {
    "home_bg","hero_bg","house_bg","treasury","shop","development",
    "factions","map","games_bg","inventory_bg","loading_bg","app_logo",
    "topbar_bg","nav_bg","card_texture","frame_hero","frame_house",
    "icon_hero","icon_house","icon_treasury","icon_shop","icon_map",
    "icon_games","icon_factions","icon_inventory","icon_development",
    "icon_daily","duel_bg","duel_frame","duel_vs","icon_customization",
    "tarot_bg","tarot_back","icon_tarot","npc_bg","icon_npc","room_bg",
    "enemy_dragon_1","enemy_dragon_2","enemy_dragon_3",
    "enemy_monster_1","enemy_monster_2","enemy_monster_3",
    "enemy_anomaly_1","enemy_anomaly_2","enemy_anomaly_3",
    "guard_model_1","guard_model_2","guard_model_3",
    "peasant_model_1","peasant_model_2","peasant_model_3",
    "npc_peasant_1",
    "npc_peasant_2",
    "npc_peasant_3",
    "npc_farmer_1",
    "npc_farmer_2",
    "npc_farmer_3",
    "npc_gardener_1",
    "npc_gardener_2",
    "npc_gardener_3",
    "npc_forester_1",
    "npc_forester_2",
    "npc_forester_3",
    "npc_miner_1",
    "npc_miner_2",
    "npc_miner_3",
    "npc_fisher_1",
    "npc_fisher_2",
    "npc_fisher_3",
    "npc_cook_1",
    "npc_cook_2",
    "npc_cook_3",
    "npc_recruit_1",
    "npc_recruit_2",
    "npc_recruit_3",
    "npc_guard_1",
    "npc_guard_2",
    "npc_guard_3",
    "npc_veteran_1",
    "npc_veteran_2",
    "npc_veteran_3",
    "npc_archer_1",
    "npc_archer_2",
    "npc_archer_3",
    "npc_rider_1",
    "npc_rider_2",
    "npc_rider_3",
    "npc_paladin_1",
    "npc_paladin_2",
    "npc_paladin_3",
    "npc_dragon_tamer_1",
    "npc_dragon_tamer_2",
    "npc_dragon_tamer_3",
    "npc_mage_1",
    "npc_mage_2",
    "npc_mage_3",
    "npc_seer_1",
    "npc_seer_2",
    "npc_seer_3",
    "npc_alchemist_1",
    "npc_alchemist_2",
    "npc_alchemist_3",
    "npc_exorcist_1",
    "npc_exorcist_2",
    "npc_exorcist_3",
    "npc_archmage_1",
    "npc_archmage_2",
    "npc_archmage_3",
    "npc_merchant_1",
    "npc_merchant_2",
    "npc_merchant_3",
    "npc_banker_1",
    "npc_banker_2",
    "npc_banker_3",
    "npc_quartermaster_1",
    "npc_quartermaster_2",
    "npc_quartermaster_3",
    "npc_treasurer_1",
    "npc_treasurer_2",
    "npc_treasurer_3",
    "npc_judge_1",
    "npc_judge_2",
    "npc_judge_3",
    "npc_scribe_1",
    "npc_scribe_2",
    "npc_scribe_3",
    "npc_advisor_1",
    "npc_advisor_2",
    "npc_advisor_3",
    "npc_chancellor_1",
    "npc_chancellor_2",
    "npc_chancellor_3",
    "npc_bard_1",
    "npc_bard_2",
    "npc_bard_3",
    "npc_artist_1",
    "npc_artist_2",
    "npc_artist_3",
    "npc_librarian_1",
    "npc_librarian_2",
    "npc_librarian_3",
    "npc_architect_1",
    "npc_architect_2",
    "npc_architect_3",
    "npc_dog_1",
    "npc_dog_2",
    "npc_dog_3",
    "npc_cat_1",
    "npc_cat_2",
    "npc_cat_3",
    "npc_falcon_1",
    "npc_falcon_2",
    "npc_falcon_3",
    "npc_small_dragon_1",
    "npc_small_dragon_2",
    "npc_small_dragon_3",
    "npc_royal_architect_1",
    "npc_royal_architect_2",
    "npc_royal_architect_3",
    "npc_great_magister_1",
    "npc_great_magister_2",
    "npc_great_magister_3",
    "npc_royal_general_1",
    "npc_royal_general_2",
    "npc_royal_general_3",
    "npc_forest_keeper_1",
    "npc_forest_keeper_2",
    "npc_forest_keeper_3",
    "npc_angel_of_light_1",
    "npc_angel_of_light_2",
    "npc_angel_of_light_3"
}

async def duel_character_payload(session, character: Character):
    stats = await get_equipment_bonuses(session, character.id)
    total = lambda key: int(getattr(character, key)) + int(stats.get(key, 0))
    return {
        "id": character.id,
        "name": character.name,
        "level": character.level,
        "title": character.title,
        "rating": character.duel_rating,
        "wins": character.duel_wins,
        "losses": character.duel_losses,
        "streak": character.duel_win_streak,
        "image_url": f"/api/miniapp/duel-image/{character.id}",
        "stats": {key: total(key) for key in (
            "health","mana","strength","intelligence","agility",
            "magic","luck","endurance","charisma"
        )},
    }

async def duel_payload(session, duel: Duel, viewer: Character):
    challenger = await session.get(Character, duel.challenger_id)
    opponent = await session.get(Character, duel.opponent_id)
    mine = "challenger" if viewer.id == duel.challenger_id else "opponent"
    return {
        "id": duel.id,
        "status": duel.status,
        "round": duel.round_number,
        "viewer_side": mine,
        "is_my_turn": duel.turn_character_id == viewer.id,
        "winner_id": duel.winner_id,
        "challenger": await duel_character_payload(session, challenger),
        "opponent": await duel_character_payload(session, opponent),
        "battle": {
            "challenger_hp": duel.challenger_hp,
            "opponent_hp": duel.opponent_hp,
            "challenger_mana": duel.challenger_mana,
            "opponent_mana": duel.opponent_mana,
            "challenger_stamina": duel.challenger_stamina,
            "opponent_stamina": duel.opponent_stamina,
            "challenger_style": duel.challenger_style,
            "opponent_style": duel.opponent_style,
            "log": log_list(duel),
        },
    }

@router.get("/duels")
async def duel_center(user=Depends(current_miniapp_user), session:AsyncSession=Depends(get_session)):
    me = await require_character(user, session)
    players_result = await session.execute(
        select(Character).where(Character.id != me.id).order_by(Character.duel_rating.desc(), Character.name)
    )
    players = [await duel_character_payload(session, c) for c in players_result.scalars()]
    duels_result = await session.execute(
        select(Duel).where(
            (Duel.challenger_id == me.id) | (Duel.opponent_id == me.id)
        ).order_by(Duel.id.desc()).limit(20)
    )
    duels = list(duels_result.scalars())
    active = next((d for d in duels if d.status == "active"), None)
    incoming = [await duel_payload(session,d,me) for d in duels if d.status=="invited" and d.opponent_id==me.id]
    outgoing = [await duel_payload(session,d,me) for d in duels if d.status=="invited" and d.challenger_id==me.id]
    history = [await duel_payload(session,d,me) for d in duels if d.status in {"finished","declined"}][:10]
    return {
        "me": await duel_character_payload(session, me),
        "styles": [{"key":k,"name":v["name"]} for k,v in STYLES.items()],
        "players": players,
        "active": await duel_payload(session,active,me) if active else None,
        "incoming": incoming,
        "outgoing": outgoing,
        "history": history,
    }

@router.post("/duels/challenge")
async def duel_challenge(payload:DuelChallengeRequest,user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    me=await require_character(user,session)
    if payload.style not in STYLES: raise HTTPException(400,"Неизвестный боевой стиль")
    opponent=await session.get(Character,payload.opponent_id)
    if not opponent or opponent.id==me.id: raise HTTPException(404,"Соперник не найден")
    busy=await session.scalar(select(Duel.id).where(
        ((Duel.challenger_id.in_([me.id,opponent.id])) | (Duel.opponent_id.in_([me.id,opponent.id]))),
        Duel.status.in_(["invited","active"]),
    ))
    if busy: raise HTTPException(400,"Один из игроков уже участвует в дуэли")
    duel=Duel(chat_id=0,challenger_id=me.id,opponent_id=opponent.id,challenger_style=payload.style,status="invited")
    session.add(duel); await session.flush()
    return {"ok":True,"duel_id":duel.id}

@router.post("/duels/{duel_id}/accept")
async def duel_accept(duel_id:int,payload:DuelAcceptRequest,user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    me=await require_character(user,session); duel=await session.get(Duel,duel_id)
    if not duel or duel.opponent_id!=me.id or duel.status!="invited": raise HTTPException(404,"Приглашение недоступно")
    if payload.style not in STYLES: raise HTTPException(400,"Неизвестный стиль")
    challenger=await session.get(Character,duel.challenger_id)
    duel.opponent_style=payload.style
    await initialize_duel(session,duel,challenger,me)
    return await duel_payload(session,duel,me)

@router.post("/duels/{duel_id}/decline")
async def duel_decline(duel_id:int,user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    me=await require_character(user,session); duel=await session.get(Duel,duel_id)
    if not duel or duel.opponent_id!=me.id or duel.status!="invited": raise HTTPException(404,"Приглашение недоступно")
    duel.status="declined"; duel.finished_at=datetime.now(timezone.utc)
    return {"ok":True}

@router.get("/duels/{duel_id}")
async def duel_state(duel_id:int,user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    me=await require_character(user,session); duel=await session.get(Duel,duel_id)
    if not duel or me.id not in {duel.challenger_id,duel.opponent_id}: raise HTTPException(404,"Дуэль не найдена")
    return await duel_payload(session,duel,me)

@router.post("/duels/{duel_id}/action")
async def duel_action(duel_id:int,payload:DuelActionRequest,user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    me=await require_character(user,session); duel=await session.get(Duel,duel_id)
    if not duel or duel.status!="active" or me.id not in {duel.challenger_id,duel.opponent_id}: raise HTTPException(404,"Активная дуэль не найдена")
    if duel.turn_character_id!=me.id: raise HTTPException(400,"Сейчас ход соперника")
    target_id=duel.opponent_id if me.id==duel.challenger_id else duel.challenger_id
    target=await session.get(Character,target_id)
    try:
        finished,_=await perform_action(session,duel,me,target,payload.action)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    if finished:
        duel.finished_at=datetime.now(timezone.utc)
        me.duel_wins+=1; me.duel_win_streak+=1; target.duel_losses+=1; target.duel_win_streak=0
        rating_gain=12+min(18,max(0,target.duel_rating-me.duel_rating)//25)
        me.duel_rating+=rating_gain; target.duel_rating=max(0,target.duel_rating-rating_gain)
        reward_gold=max(3,int((4+target.level//3)*level_income_multiplier(me.level)))
        reward_xp=20+target.level
        await change_gold(session,me,reward_gold,"miniapp_duel_win")
        me.experience+=reward_xp; target.experience+=5
        apply_levels(me); apply_levels(target)
    return await duel_payload(session,duel,me)

@router.get("/duel-image/{character_id}")
async def duel_image(character_id:int,user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    await require_character(user,session)
    character=await session.get(Character,character_id)
    if not character or not character.portrait_file_id: raise HTTPException(404,"Портрет не найден")
    return await telegram_file_response(character.portrait_file_id)

@router.get("/admin/theme")
async def admin_theme(user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    from app.config import get_settings
    if user.id not in get_settings().admins: raise HTTPException(403,"Недостаточно прав")
    return {"keys":sorted(THEME_KEYS),"media":{k:(f"/api/miniapp/media/{k}" if await get_system_media(session,k) else None) for k in THEME_KEYS}}

@router.post("/admin/theme/{key}")
async def admin_theme_upload(key:str,file:UploadFile=File(...),user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    from app.config import get_settings
    if user.id not in get_settings().admins: raise HTTPException(403,"Недостаточно прав")
    if key not in THEME_KEYS: raise HTTPException(404,"Элемент оформления не найден")
    content=await file.read()
    if not content or len(content)>10*1024*1024: raise HTTPException(400,"Файл пустой или больше 10 МБ")
    bot=Bot(get_settings().bot_token)
    try:
        sent=await bot.send_photo(user.id,BufferedInputFile(content,filename=file.filename or "theme.jpg"),caption=f"🎨 Обновлено оформление: {key}")
        file_id=sent.photo[-1].file_id
    finally:
        await bot.session.close()
    await set_system_media(session,key,file_id)
    return {"ok":True,"key":key,"url":f"/api/miniapp/media/{key}"}


@router.delete("/admin/theme/{key}")
async def admin_theme_delete(
    key: str,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    from app.config import get_settings
    if user.id not in get_settings().admins:
        raise HTTPException(403, "Недостаточно прав")
    if key not in THEME_KEYS:
        raise HTTPException(404, "Элемент оформления не найден")
    result = await session.execute(select(SystemMedia).where(SystemMedia.key == key))
    media = result.scalar_one_or_none()
    if media:
        await session.delete(media)
    return {"ok": True, "key": key}


@router.delete("/profile/portrait")
async def delete_own_portrait(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    character.portrait_file_id = None
    return {"ok": True}


@router.delete("/profile/house-image")
async def delete_own_house_image(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    if not character.house:
        raise HTTPException(404, "Дом не найден")
    character.house.image_file_id = None
    return {"ok": True}


class TarotReadingRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    choice_index: Literal[0, 1, 2]


async def tarot_card_payload(session: AsyncSession, card: TarotCard) -> dict:
    owner_name = "Стандартная колода"
    if card.owner_character_id:
        owner = await session.get(Character, card.owner_character_id)
        owner_name = owner.name if owner else "Неизвестный гражданин"
    return {
        "id": card.id,
        "name": card.name,
        "suit": card.suit,
        "number": card.number,
        "description": card.description,
        "upright_meaning": card.upright_meaning,
        "reversed_meaning": card.reversed_meaning,
        "is_standard": card.is_standard,
        "owner_name": owner_name,
        "image_url": (
            f"/api/miniapp/tarot/cards/{card.id}/image"
            if card.image_file_id
            else None
        ),
    }


@router.get("/tarot")
async def tarot_center(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    cards_result = await session.execute(
        select(TarotCard).order_by(
            TarotCard.is_standard.asc(),
            TarotCard.created_at.desc(),
            TarotCard.id,
        )
    )
    cards = [
        await tarot_card_payload(session, card)
        for card in cards_result.scalars()
    ]

    history_result = await session.execute(
        select(TarotReading, TarotCard)
        .join(TarotCard, TarotCard.id == TarotReading.card_id)
        .where(TarotReading.character_id == character.id)
        .order_by(TarotReading.id.desc())
        .limit(20)
    )
    history = [{
        "id": reading.id,
        "question": reading.question,
        "orientation": reading.orientation,
        "prediction": reading.prediction,
        "reading_date": reading.reading_date,
        "card": await tarot_card_payload(session, card),
    } for reading, card in history_result.all()]

    today = local_date()
    today_reading = next(
        (item for item in history if item["reading_date"] == today),
        None,
    )

    return {
        "cards": cards,
        "history": history,
        "today_reading": today_reading,
        "can_ask_today": True,
        "disclaimer": (
            "Предсказание является игровой интерпретацией и создано "
            "для развлечения и размышления."
        ),
    }


@router.post("/tarot/cards")
async def upload_tarot_card(
    name: str = Form(...),
    suit: str = Form("Авторская карта"),
    description: str = Form(""),
    upright_meaning: str = Form(...),
    reversed_meaning: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    clean_name = name.strip()
    if not clean_name or len(clean_name) > 100:
        raise HTTPException(400, "Название должно содержать от 1 до 100 символов.")
    if len(upright_meaning.strip()) < 3 or len(reversed_meaning.strip()) < 3:
        raise HTTPException(400, "Добавьте значения карты.")

    content = await file.read()
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Файл пустой или больше 10 МБ.")

    from app.config import get_settings
    bot = Bot(get_settings().bot_token)
    try:
        sent = await bot.send_photo(
            user.id,
            BufferedInputFile(
                content,
                filename=file.filename or "tarot-card.jpg",
            ),
            caption=f"🔮 Карта добавлена в общую галерею: {clean_name}",
        )
        file_id = sent.photo[-1].file_id
    finally:
        await bot.session.close()

    card = TarotCard(
        owner_character_id=character.id,
        name=clean_name,
        suit=suit.strip()[:64] or "Авторская карта",
        description=description.strip()[:2000],
        upright_meaning=upright_meaning.strip()[:2000],
        reversed_meaning=reversed_meaning.strip()[:2000],
        image_file_id=file_id,
        is_standard=False,
    )
    session.add(card)
    await session.flush()
    return {
        "ok": True,
        "card": await tarot_card_payload(session, card),
    }


@router.get("/tarot/cards/{card_id}/image")
async def tarot_card_image(
    card_id: int,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    await require_character(user, session)
    card = await session.get(TarotCard, card_id)
    if not card or not card.image_file_id:
        raise HTTPException(404, "Изображение карты не найдено.")
    return await telegram_file_response(card.image_file_id)


@router.post("/tarot/offer")
async def tarot_offer(
    payload: dict,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    question = str(payload.get("question", "")).strip()
    if len(question) < 3 or len(question) > 500:
        raise HTTPException(400, "Введите вопрос длиной от 3 до 500 символов.")

    cards = await offered_cards(session, character, question)
    return {
        "cards": [{
            "position": index,
            "back_url": (
                "/api/miniapp/media/tarot_back"
                if await get_system_media(session, "tarot_back")
                else None
            ),
        } for index, _card in enumerate(cards)],
    }


@router.post("/tarot/reading")
async def tarot_reading(
    payload: TarotReadingRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    try:
        reading = await create_daily_reading(
            session,
            character,
            payload.question,
            payload.choice_index,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    card = await session.get(TarotCard, reading.card_id)
    return {
        "ok": True,
        "reading": {
            "id": reading.id,
            "question": reading.question,
            "orientation": reading.orientation,
            "prediction": reading.prediction,
            "reading_date": reading.reading_date,
            "card": await tarot_card_payload(session, card),
        },
    }


class MonsterActionRequest(BaseModel):
    action: Literal["attack", "magic", "defend", "dodge", "critical", "potion"]


class NpcBuyRequest(BaseModel):
    npc_type: Literal["guard", "peasant"]


class NpcActionRequest(BaseModel):
    npc_id: int
    action: str


def unlocked_room_count(level: int) -> int:
    return 1 + level // 3


async def active_house_attack(session: AsyncSession, house_id: int):
    return await session.scalar(
        select(HouseAttack)
        .where(
            HouseAttack.house_id == house_id,
            HouseAttack.status.in_(["waiting", "player_fighting", "guards_fighting"]),
        )
        .order_by(HouseAttack.id.desc())
    )


async def npc_payload(npc: NpcUnit) -> dict:
    remaining = 0
    if npc.available_at:
        remaining = max(
            0,
            int((npc.available_at - datetime.now(timezone.utc)).total_seconds()),
        )
    return {
        "id": npc.id,
        "type": npc.npc_type,
        "name": npc.name,
        "model_variant": npc.model_variant,
        "level": npc.level,
        "experience": npc.experience,
        "fatigue": npc.fatigue,
        "status": npc.status,
        "assignment": npc.assignment,
        "remaining_seconds": remaining,
        "alive": npc.alive,
        "model_url": f"/api/miniapp/media/{npc.npc_type}_model_{npc.model_variant}"
            if npc.npc_type in {"guard", "peasant"} else None,
    }


@router.get("/estate")
async def estate_center(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    house = character.house
    if not house:
        raise HTTPException(404, "Владение не найдено.")

    rooms_result = await session.execute(
        select(HouseRoom)
        .where(HouseRoom.house_id == house.id)
        .order_by(HouseRoom.id)
    )
    rooms = list(rooms_result.scalars())
    if not rooms:
        default_room = HouseRoom(
            house_id=house.id,
            name="Главная комната",
            description="Первая открытая комната вашего владения.",
            cleanliness=house.cleanliness,
        )
        session.add(default_room)
        await session.flush()
        rooms = [default_room]
    attack = await active_house_attack(session, house.id)

    attack_data = None
    if attack:
        variant = (attack.id % 3) + 1
        media_type = (
            "dragon" if attack.enemy_type == "dragon"
            else "anomaly" if attack.enemy_type == "anomaly"
            else "monster"
        )
        attack_data = {
            "id": attack.id,
            "enemy_name": attack.enemy_name,
            "enemy_type": attack.enemy_type,
            "enemy_power": attack.enemy_power,
            "enemy_hp": attack.enemy_hp,
            "player_hp": attack.player_hp,
            "player_mana": attack.player_mana,
            "status": attack.status,
            "guards_used": attack.guards_used,
            "response_deadline": attack.response_deadline.isoformat(),
            "guard_finish_at": (
                attack.guard_finish_at.isoformat()
                if attack.guard_finish_at else None
            ),
            "enemy_image_url": f"/api/miniapp/media/enemy_{media_type}_{variant}",
        }

    return {
        "house": {
            "id": house.id,
            "name": house.name,
            "integrity": house.integrity,
            "cleanliness": house.cleanliness,
            "last_cleaning_date": house.last_cleaning_date,
            "threat_level": house.threat_level,
            "cleaning_available": house.last_cleaning_date != local_date(),
        },
        "room_limit": unlocked_room_count(character.level),
        "rooms": [{
            "id": room.id,
            "name": room.name,
            "description": room.description,
            "cleanliness": room.cleanliness,
            "image_url": (
                f"/api/miniapp/estate/rooms/{room.id}/image"
                if room.image_file_id else None
            ),
        } for room in rooms],
        "attack": attack_data,
    }


@router.post("/estate/rooms")
async def add_room(
    name: str = Form(...),
    description: str = Form(""),
    file: UploadFile | None = File(None),
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    house = character.house
    room_count = await session.scalar(
        select(__import__("sqlalchemy", fromlist=["func"]).func.count(HouseRoom.id))
        .where(HouseRoom.house_id == house.id)
    )
    if room_count >= unlocked_room_count(character.level):
        next_level = ((room_count) * 3)
        raise HTTPException(
            400,
            f"Новый слот комнаты откроется на {next_level} уровне героя.",
        )

    file_id = None
    if file:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(400, "Изображение больше 10 МБ.")
        from app.config import get_settings
        bot = Bot(get_settings().bot_token)
        try:
            sent = await bot.send_photo(
                user.id,
                BufferedInputFile(content, filename=file.filename or "room.jpg"),
                caption=f"🏠 Добавлена комната: {name.strip()[:100]}",
            )
            file_id = sent.photo[-1].file_id
        finally:
            await bot.session.close()

    room = HouseRoom(
        house_id=house.id,
        name=name.strip()[:100],
        description=description.strip()[:2000],
        image_file_id=file_id,
    )
    session.add(room)
    await session.flush()
    return {"ok": True, "room_id": room.id}


@router.get("/estate/rooms/{room_id}/image")
async def room_image(
    room_id: int,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    room = await session.get(HouseRoom, room_id)
    if not room or room.house_id != character.house.id or not room.image_file_id:
        raise HTTPException(404, "Изображение комнаты не найдено.")
    return await telegram_file_response(room.image_file_id)


@router.post("/estate/clean")
async def clean_estate(
    payload: dict,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    house = character.house
    if house.last_cleaning_date == local_date():
        raise HTTPException(400, "Сегодня уборка уже проведена.")

    method = str(payload.get("method", "self"))
    if method == "peasant":
        peasant = await session.scalar(
            select(NpcUnit).where(
                NpcUnit.character_id == character.id,
                NpcUnit.npc_type == "peasant",
                NpcUnit.alive.is_(True),
                NpcUnit.status == "idle",
                NpcUnit.fatigue < 90,
            ).order_by(NpcUnit.fatigue, NpcUnit.id)
        )
        if not peasant:
            raise HTTPException(400, "Нет свободного и неуставшего крестьянина.")
        peasant.fatigue = min(100, peasant.fatigue + 22)
        peasant.experience += 8
        peasant.assignment = "cleaning"
        peasant.status = "working"
        peasant.available_at = datetime.now(timezone.utc) + timedelta(minutes=20)
    else:
        character.experience += 5
        apply_levels(character)

    house.cleanliness = 100
    house.last_cleaning_date = local_date()
    rooms_result = await session.execute(
        select(HouseRoom).where(HouseRoom.house_id == house.id)
    )
    for room in rooms_result.scalars():
        room.cleanliness = 100
    return {"ok": True, "cleanliness": 100}


@router.post("/estate/attack/start")
async def start_monster_fight(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    attack = await active_house_attack(session, character.house.id)
    if not attack or attack.status != "waiting":
        raise HTTPException(400, "Нет доступного нападения.")
    stats = await get_effective_stats(session, character)
    attack.status = "player_fighting"
    attack.defender_character_id = character.id
    attack.player_hp = stats["health"] + stats["endurance"] * 2 + character.level * 3
    attack.player_mana = stats["mana"] + stats["intelligence"]
    return {"ok": True}


@router.post("/estate/attack/action")
async def monster_fight_action(
    payload: MonsterActionRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    house = character.house
    attack = await active_house_attack(session, house.id)
    if not attack or attack.status != "player_fighting":
        raise HTTPException(400, "Активный бой не найден.")
    if attack.defender_character_id != character.id:
        raise HTTPException(403, "Сейчас сражается другой защитник.")

    stats = await get_effective_stats(session, character)
    action = payload.action
    player_log = ""
    defended = False

    if action == "potion":
        if attack.player_hp >= stats["health"] + stats["endurance"] * 2 + character.level * 3:
            raise HTTPException(400, "Здоровье уже заполнено.")
        heal = 18 + stats["intelligence"] // 2 + randint(0, 16)
        attack.player_hp += heal
        player_log = f"🧪 Вы восстановили {heal} здоровья."
    elif action == "defend":
        defended = True
        player_log = "🛡 Вы приготовились принять удар."
    elif action == "dodge":
        chance = min(65, 18 + stats["agility"] + stats["luck"] // 3)
        if randint(1, 100) <= chance:
            player_log = "💨 Вы полностью уклонились от атаки врага."
            return {
                "ok": True,
                "finished": False,
                "player_log": player_log,
                "enemy_log": "Враг промахнулся.",
                "player_hp": attack.player_hp,
                "player_mana": attack.player_mana,
                "enemy_hp": attack.enemy_hp,
            }
        player_log = "💨 Попытка уклонения не удалась."
    else:
        random_half = randint(8, 28) + randint(0, max(5, attack.enemy_power // 5))
        if action == "magic":
            cost = 12
            if attack.player_mana < cost:
                raise HTTPException(400, "Недостаточно маны.")
            attack.player_mana -= cost
            stat_half = stats["magic"] + stats["intelligence"] // 2 + character.level
        else:
            stat_half = stats["strength"] + stats["agility"] // 3 + character.level
        damage = max(1, int((stat_half + random_half) / 2))
        if action == "critical":
            chance = min(55, 12 + stats["luck"] // 2)
            if randint(1, 100) <= chance:
                damage = int(damage * 1.8)
                player_log = f"💥 Критический удар наносит {damage} урона."
            else:
                damage = max(1, damage // 2)
                player_log = f"⚠ Крит не сработал: {damage} урона."
        else:
            player_log = f"⚔ Вы наносите {damage} урона."
        attack.enemy_hp = max(0, attack.enemy_hp - damage)

    if attack.enemy_hp <= 0:
        attack.status = "owner_won"
        attack.finished_at = datetime.now(timezone.utc)
        reward_xp = 20 + attack.enemy_power // 3
        reward_gold = max(2, attack.enemy_power // 12)
        character.experience += reward_xp
        await change_gold(session, character, reward_gold, "monster_defense")
        house.repair_energy += randint(6, 14)
        house.threat_level += 1
        apply_levels(character)
        return {
            "ok": True,
            "finished": True,
            "victory": True,
            "player_log": player_log,
            "reward_xp": reward_xp,
            "reward_gold": reward_gold,
        }

    enemy_random = randint(7, 24)
    enemy_stat = attack.enemy_power + house.threat_level * 2
    enemy_damage = max(1, int((enemy_random + enemy_stat // 3) / 2))
    protection = min(55, stats["endurance"] + character.level)
    enemy_damage = max(1, int(enemy_damage * (100 - protection) / 100))
    if defended:
        enemy_damage = max(1, enemy_damage // 2)
    attack.player_hp = max(0, attack.player_hp - enemy_damage)
    enemy_log = f"👹 Враг наносит {enemy_damage} урона."

    if attack.player_hp <= 0:
        damage_house = randint(12, 28)
        house.integrity = max(0, house.integrity - damage_house)
        attack.status = "enemy_won"
        attack.damage_done = damage_house
        attack.finished_at = datetime.now(timezone.utc)
        house.threat_level += 1
        return {
            "ok": True,
            "finished": True,
            "victory": False,
            "player_log": player_log,
            "enemy_log": enemy_log,
            "house_damage": damage_house,
        }

    return {
        "ok": True,
        "finished": False,
        "player_log": player_log,
        "enemy_log": enemy_log,
        "player_hp": attack.player_hp,
        "player_mana": attack.player_mana,
        "enemy_hp": attack.enemy_hp,
    }


@router.get("/npcs")
async def npc_center(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    result = await session.execute(
        select(NpcUnit)
        .where(NpcUnit.character_id == character.id)
        .order_by(NpcUnit.alive.desc(), NpcUnit.npc_type, NpcUnit.id)
    )
    units = list(result.scalars())
    return {
        "prices": {"guard": 80, "peasant": 70},
        "units": [await npc_payload(unit) for unit in units],
        "rules": {
            "guard_time": "1 стражник — 30 минут; каждый следующий сокращает бой на 3,5 минуты.",
            "fatigue": "При усталости 100 крестьянин нуждается в отдыхе. Без отдыха он может погибнуть.",
            "school": "Обучение стражника длится 4 часа и повышает его уровень.",
        },
    }


@router.post("/npcs/buy")
async def buy_npc_unit(
    payload: NpcBuyRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    price = 80 if payload.npc_type == "guard" else 70
    await change_gold(session, character, -price, f"buy_npc:{payload.npc_type}")
    count = await session.scalar(
        select(__import__("sqlalchemy", fromlist=["func"]).func.count(NpcUnit.id))
        .where(
            NpcUnit.character_id == character.id,
            NpcUnit.npc_type == payload.npc_type,
        )
    )
    index = int(count or 0) + 1
    unit = NpcUnit(
        character_id=character.id,
        npc_type=payload.npc_type,
        name=("Стражник" if payload.npc_type == "guard" else "Крестьянин") + f" №{index}",
        model_variant=((index - 1) % 3) + 1,
    )
    session.add(unit)
    await session.flush()
    return {"ok": True, "unit": await npc_payload(unit), "gold": character.gold}


@router.post("/npcs/action")
async def npc_action(
    payload: NpcActionRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    npc = await session.get(NpcUnit, payload.npc_id)
    if not npc or npc.character_id != character.id or not npc.alive:
        raise HTTPException(404, "NPC не найден.")

    now = datetime.now(timezone.utc)
    if npc.available_at and npc.available_at > now:
        raise HTTPException(400, "NPC сейчас занят.")
    if npc.available_at and npc.available_at <= now:
        if npc.status == "resting":
            npc.fatigue = max(0, npc.fatigue - 70)
        elif npc.status == "training":
            npc.level += 1
            npc.experience = 0
        npc.status = "idle"
        npc.assignment = None
        npc.available_at = None

    action = payload.action
    if action == "rest":
        npc.status = "resting"
        npc.assignment = "rest"
        npc.available_at = now + timedelta(hours=8)
        npc.last_rest_at = now
        return {"ok": True, "message": "NPC отдыхает 8 часов."}

    if npc.npc_type == "guard":
        if action != "school":
            raise HTTPException(400, "Стражнику доступно обучение в школе.")
        await change_gold(session, character, -10, "guard_school")
        npc.status = "training"
        npc.assignment = "school"
        npc.available_at = now + timedelta(hours=4)
        return {"ok": True, "message": "Стражник отправлен в Королевскую школу на 4 часа."}

    if npc.fatigue >= 90:
        raise HTTPException(400, "Крестьянин слишком устал. Сначала отправьте его отдыхать.")

    task_map = {
        "field": (30, 60, "Работа в поле"),
        "clean": (22, 20, "Уборка владения"),
        "garden": (20, 25, "Полив сада"),
        "toilets": (26, 15, "Чистка туалетов"),
    }
    if action not in task_map:
        raise HTTPException(400, "Неизвестное поручение.")

    fatigue, minutes, label = task_map[action]
    npc.fatigue = min(100, npc.fatigue + fatigue)
    npc.status = "working"
    npc.assignment = action
    npc.available_at = now + timedelta(minutes=minutes)
    npc.experience += 6 + npc.level

    if action == "field":
        reward = randint(2, 5) + npc.level
        await change_gold(session, character, reward, "peasant_field")
        message = f"{label}: получено {reward} золота."
    elif action == "clean":
        character.house.cleanliness = 100
        character.house.last_cleaning_date = local_date()
        message = "Владение убрано."
    elif action == "garden":
        character.house.repair_energy += 3 + npc.level
        message = "Сад полит, получена энергия ремонта."
    else:
        character.experience += 4
        apply_levels(character)
        message = "Туалеты очищены. Получено 4 XP."

    if npc.fatigue >= 100 and randint(1, 100) <= 35:
        npc.alive = False
        npc.status = "dead"
        message += " NPC погиб от истощения."
    return {"ok": True, "message": message, "unit": await npc_payload(npc)}
