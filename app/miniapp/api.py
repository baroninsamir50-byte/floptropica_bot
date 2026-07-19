from random import randint, choice
from datetime import datetime, timezone, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from aiogram import Bot
from aiogram.types import BufferedInputFile
from io import BytesIO
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    get_effective_stats, household_members, GUARD_UPGRADE_ITEMS,
    FARMER_UPGRADE_ITEMS, NPC_UPGRADE_ITEMS, WORK_REWARD_MULTIPLIER,
    guard_model_variant,
)
from app.work_catalog import available_professions, profession_by_key, title_can_use
from app.miniapp.duel_engine import STYLES, initialize_duel, perform_action, log_list
from app.tarot_service import create_daily_reading, offered_cards
from app.factions import (
    FACTIONS, TITLES, VIEW_LABELS, faction_development_bonus,
    faction_payload, normalize_faction,
)

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


async def database_user(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def has_project_admin_rights(session: AsyncSession, telegram_id: int) -> bool:
    from app.config import get_settings
    if telegram_id in get_settings().admins:
        return True
    db_user = await database_user(session, telegram_id)
    return bool(db_user and db_user.is_admin)


async def require_project_admin(session: AsyncSession, telegram_id: int) -> User | None:
    if not await has_project_admin_rights(session, telegram_id):
        raise HTTPException(403, "Недостаточно прав")
    return await database_user(session, telegram_id)


def standard_tarot_image_url(card: TarotCard) -> str | None:
    if not card.is_standard:
        return None
    base = "https://raw.githubusercontent.com/searge/tarot/master/assets/img/big"
    if card.suit == "Старшие Арканы" and card.number is not None:
        return f"{base}/maj{int(card.number):02d}.jpg"
    prefixes = {"Кубки":"cups","Мечи":"swords","Пентакли":"pents","Жезлы":"wands"}
    prefix = prefixes.get(card.suit)
    if prefix and card.number is not None:
        return f"{base}/{prefix}{int(card.number):02d}.jpg"
    return None

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
    c.faction = normalize_faction(c.faction)
    c.user.last_seen_at = datetime.now(timezone.utc)
    household, household_ids, household_houses, shared_house = await household_context(session, c)
    spouse = next((member for member in household if member.id != c.id), None)
    bonuses = await get_equipment_bonuses(session, c.id)
    total = lambda k: int(getattr(c,k)) + int(bonuses.get(k,0))
    shop = await get_daily_shop_items(session, 6)
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
        "spouse": ({"id": spouse.id, "name": spouse.name} if spouse else None),
        "faction_bonus": faction_payload(c.faction),
        "reputation":c.reputation,"development_points":c.development_points,
        "portrait_available": bool(c.portrait_file_id),
        "rank":level_rank(c.level),"income_multiplier":round(level_income_multiplier(c.level),2),
        "login_streak":c.login_streak,"daily_reward_available":c.daily_reward_date != local_date(),
        "stats":{k:total(k) for k in ("health","mana","strength","intelligence","agility","magic","luck","endurance","charisma")}},
        "house":{"name":shared_house.name if shared_house else None,"location":shared_house.location if shared_house else None,
        "description":shared_house.description if shared_house else None,"level":shared_house.level if shared_house else None,
        "value":shared_house.value if shared_house else None,"defense":shared_house.defense if shared_house else None,
        "integrity":shared_house.integrity if shared_house else None,
        "repair_energy":shared_house.repair_energy if shared_house else None,
        "shared": bool(spouse), "spouse_name": spouse.name if spouse else None,
        "image_available": bool(shared_house and shared_house.image_file_id)},
        "work":{"count":c.work_count,"active":bool(c.work_ends_at and not c.work_reward_claimed),"remaining_seconds":remaining},
        "professions":[{"key":k,"name":str(d["name"]),"label":str(d["label"]),
            "gold":[max(1, int(d["gold"][0] * level_income_multiplier(c.level) * WORK_REWARD_MULTIPLIER)), max(1, int(d["gold"][1] * level_income_multiplier(c.level) * WORK_REWARD_MULTIPLIER))],
            "xp":list(d["xp"])} for k,d in available_professions(c.title)],
        "shop":{"date":local_date(),"items":[{"id":i.id,"name":i.name,"description":i.description,"price":i.price,
            "slot":i.slot,"rarity":i.rarity,"stat_name":i.stat_name,"stat_bonus":i.stat_bonus} for i in shop]},
        "inventory":inventory,"npcs":npcs,"media":media,
        "is_admin": await has_project_admin_rights(session, user.id),
        "is_owner": user.id in __import__("app.config", fromlist=["get_settings"]).get_settings().admins,
    }

@router.post("/development")
async def development(payload: DevelopmentRequest,user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    c=await require_character(user,session)
    if c.development_points<payload.amount: raise HTTPException(400,"Недостаточно очков развития")
    c.development_points -= payload.amount
    bonus = faction_development_bonus(c.faction, payload.stat, payload.amount)
    gained = payload.amount + bonus
    setattr(c, payload.stat, getattr(c, payload.stat) + gained)
    return {"ok": True, "spent": payload.amount, "gained": gained, "faction_bonus": bonus}

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
    _, _, _, house = await household_context(session, character)
    if not house or not house.image_file_id:
        raise HTTPException(404, "Фотография дома не загружена")
    return await telegram_file_response(house.image_file_id)


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
    await require_project_admin(session, user.id)
    return {"keys":sorted(THEME_KEYS),"media":{k:(f"/api/miniapp/media/{k}" if await get_system_media(session,k) else None) for k in THEME_KEYS}}

@router.post("/admin/theme/{key}")
async def admin_theme_upload(key:str,file:UploadFile=File(...),user=Depends(current_miniapp_user),session:AsyncSession=Depends(get_session)):
    from app.config import get_settings
    await require_project_admin(session, user.id)
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
    await require_project_admin(session, user.id)
    if key not in THEME_KEYS:
        raise HTTPException(404, "Элемент оформления не найден")
    result = await session.execute(select(SystemMedia).where(SystemMedia.key == key))
    media = result.scalar_one_or_none()
    if media:
        await session.delete(media)
    return {"ok": True, "key": key}


class ProjectAdminRequest(BaseModel):
    telegram_id: int
    enabled: bool


class PlayerTitleRequest(BaseModel):
    character_id: int
    title: str = Field(min_length=1, max_length=100)


class PresenceRequest(BaseModel):
    view: str = Field(min_length=1, max_length=40)


@router.get("/admin/project-admins")
async def project_admins(user=Depends(current_miniapp_user),session: AsyncSession=Depends(get_session)):
    from app.config import get_settings
    if user.id not in get_settings().admins:
        raise HTTPException(403, "Назначать администраторов может только создатель")
    result = await session.execute(
        select(User, Character).outerjoin(Character, Character.user_id == User.id)
        .order_by(User.first_name, User.telegram_id)
    )
    return {"users":[{
        "telegram_id": db_user.telegram_id,
        "username": db_user.username,
        "first_name": db_user.first_name,
        "character_name": character.name if character else None,
        "is_project_admin": bool(db_user.is_admin),
        "is_owner": db_user.telegram_id in get_settings().admins,
    } for db_user, character in result.all()]}


@router.post("/admin/project-admins")
async def set_project_admin(payload: ProjectAdminRequest,user=Depends(current_miniapp_user),session: AsyncSession=Depends(get_session)):
    from app.config import get_settings
    if user.id not in get_settings().admins:
        raise HTTPException(403, "Назначать администраторов может только создатель")
    if payload.telegram_id in get_settings().admins:
        raise HTTPException(400, "Права создателя нельзя изменить")
    target = await database_user(session, payload.telegram_id)
    if not target:
        raise HTTPException(404, "Игрок не найден")
    target.is_admin = payload.enabled
    return {"ok":True,"telegram_id":target.telegram_id,"enabled":target.is_admin}


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
    _, _, _, house = await household_context(session, character)
    if not house:
        raise HTTPException(404, "Дом не найден")
    house.image_file_id = None
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
            else standard_tarot_image_url(card)
        ),
        "image_protected": bool(card.image_file_id),
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


class NpcUpgradeRequest(BaseModel):
    npc_id: int


class PlayerMarriageRequest(BaseModel):
    character_id: int
    spouse_character_id: int | None = None


async def household_context(session: AsyncSession, character: Character):
    members = await household_members(session, character)
    member_ids = [member.id for member in members]
    houses_result = await session.execute(
        select(House).where(House.owner_id.in_(member_ids)).order_by(House.owner_id)
    )
    houses = list(houses_result.scalars())
    primary_member = min(members, key=lambda member: member.id)
    primary_house = next((house for house in houses if house.owner_id == primary_member.id), None)
    if not primary_house and houses:
        primary_house = houses[0]
    return members, member_ids, houses, primary_house


async def household_materials(session: AsyncSession, member_ids: list[int]) -> set[str]:
    result = await session.execute(
        select(ItemTemplate.slug)
        .join(InventoryItem, InventoryItem.item_id == ItemTemplate.id)
        .where(InventoryItem.character_id.in_(member_ids), InventoryItem.quantity > 0)
    )
    return set(result.scalars())


async def consume_household_upgrade_materials(
    session: AsyncSession,
    member_ids: list[int],
    required_slugs: tuple[str, ...],
) -> None:
    """Списывает по одному предмету каждого типа из общего инвентаря семьи."""
    for slug in required_slugs:
        result = await session.execute(
            select(InventoryItem)
            .join(ItemTemplate, InventoryItem.item_id == ItemTemplate.id)
            .where(
                InventoryItem.character_id.in_(member_ids),
                ItemTemplate.slug == slug,
                InventoryItem.quantity > 0,
            )
            .order_by(InventoryItem.character_id, InventoryItem.id)
        )
        inventory_item = result.scalars().first()
        if not inventory_item:
            raise HTTPException(
                400,
                "Комплект уже неполный. Соберите заново все 5 предметов для улучшения NPC.",
            )
        if inventory_item.quantity <= 1:
            await session.delete(inventory_item)
        else:
            inventory_item.quantity -= 1


def npc_upgrade_requirements(npc_type: str) -> tuple[str, ...]:
    return GUARD_UPGRADE_ITEMS if npc_type == "guard" else FARMER_UPGRADE_ITEMS


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


async def npc_payload(
    npc: NpcUnit,
    collected_slugs: set[str] | None = None,
    owner_name: str | None = None,
) -> dict:
    remaining = 0
    if npc.available_at:
        available_at = npc.available_at
        if available_at.tzinfo is None:
            available_at = available_at.replace(tzinfo=timezone.utc)
        remaining = max(0, int((available_at - datetime.now(timezone.utc)).total_seconds()))
    collected_slugs = collected_slugs or set()
    required = npc_upgrade_requirements(npc.npc_type)
    material_names = {
        "guard_upgrade_sword": "Клинок стражи",
        "guard_upgrade_boots": "Сапоги караула",
        "guard_upgrade_shield": "Башенный щит",
        "guard_upgrade_helmet": "Шлем дозорного",
        "guard_upgrade_book": "Устав стражи",
        "farmer_upgrade_sickle": "Серп урожая",
        "farmer_upgrade_boots": "Сапоги земледельца",
        "farmer_upgrade_watering_can": "Лейка долины",
        "farmer_upgrade_hat": "Соломенная шляпа",
        "farmer_upgrade_book": "Книга агронома",
    }
    upgrade_cost = 25 + npc.upgrade_count * 15
    model_variant = guard_model_variant(npc.level) if npc.npc_type == "guard" else npc.model_variant
    if npc.npc_type == "guard" and npc.model_variant != model_variant:
        npc.model_variant = model_variant
    return {
        "id": npc.id,
        "type": npc.npc_type,
        "name": npc.name,
        "owner_character_id": npc.character_id,
        "owner_name": owner_name,
        "model_variant": model_variant,
        "level": npc.level,
        "upgrade_count": npc.upgrade_count,
        "upgrade_cost": upgrade_cost,
        "upgrade_ready": all(slug in collected_slugs for slug in required),
        "upgrade_materials": [
            {"slug": slug, "name": material_names[slug], "owned": slug in collected_slugs}
            for slug in required
        ],
        "experience": npc.experience,
        "fatigue": npc.fatigue,
        "status": npc.status,
        "assignment": npc.assignment,
        "remaining_seconds": remaining,
        "alive": npc.alive,
        "model_url": f"/api/miniapp/media/{npc.npc_type}_model_{model_variant}"
            if npc.npc_type in {"guard", "peasant"} else None,
        "appearance_rule": (
            "Фото 1: уровни 1–19 · Фото 2: уровни 20–29 · Фото 3: уровень 30+"
            if npc.npc_type == "guard" else None
        ),
    }


@router.get("/estate")
async def estate_center(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    members, member_ids, houses, house = await household_context(session, character)
    if not house:
        raise HTTPException(404, "Владение не найдено.")
    house_ids = [item.id for item in houses]

    rooms_result = await session.execute(
        select(HouseRoom)
        .where(HouseRoom.house_id.in_(house_ids))
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
            "guard_finish_at": attack.guard_finish_at.isoformat() if attack.guard_finish_at else None,
            "enemy_image_url": f"/api/miniapp/media/enemy_{media_type}_{variant}",
        }

    spouse = next((member for member in members if member.id != character.id), None)
    room_limit = sum(unlocked_room_count(member.level) for member in members)
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
        "household": {
            "shared": bool(spouse),
            "spouse_name": spouse.name if spouse else None,
            "members": [{"id": member.id, "name": member.name} for member in members],
        },
        "room_limit": room_limit,
        "rooms": [{
            "id": room.id,
            "name": room.name,
            "description": room.description,
            "cleanliness": room.cleanliness,
            "image_url": f"/api/miniapp/estate/rooms/{room.id}/image" if room.image_file_id else None,
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
    members, _, houses, house = await household_context(session, character)
    if not house:
        raise HTTPException(404, "Владение не найдено.")
    house_ids = [item.id for item in houses]
    room_count = await session.scalar(
        select(func.count(HouseRoom.id)).where(HouseRoom.house_id.in_(house_ids))
    )
    room_limit = sum(unlocked_room_count(member.level) for member in members)
    if int(room_count or 0) >= room_limit:
        raise HTTPException(400, "Все доступные слоты совместного дома уже заняты.")

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
    _, _, houses, _ = await household_context(session, character)
    house_ids = {house.id for house in houses}
    room = await session.get(HouseRoom, room_id)
    if not room or room.house_id not in house_ids or not room.image_file_id:
        raise HTTPException(404, "Изображение комнаты не найдено.")
    return await telegram_file_response(room.image_file_id)


@router.post("/estate/clean")
async def clean_estate(
    payload: dict,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    _, member_ids, houses, house = await household_context(session, character)
    if not house:
        raise HTTPException(404, "Владение не найдено.")
    if house.last_cleaning_date == local_date():
        raise HTTPException(400, "Сегодня уборка уже проведена.")

    method = str(payload.get("method", "self"))
    if method == "peasant":
        peasant = await session.scalar(
            select(NpcUnit).where(
                NpcUnit.character_id.in_(member_ids),
                NpcUnit.npc_type == "peasant",
                NpcUnit.alive.is_(True),
                NpcUnit.status == "idle",
                NpcUnit.fatigue < 90,
            ).order_by(NpcUnit.fatigue, NpcUnit.id)
        )
        if not peasant:
            raise HTTPException(400, "Нет свободного и неуставшего фермера.")
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
        select(HouseRoom).where(HouseRoom.house_id.in_([item.id for item in houses]))
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
    _, _, _, house = await household_context(session, character)
    if not house:
        raise HTTPException(404, "Владение не найдено.")
    attack = await active_house_attack(session, house.id)
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
    _, _, _, house = await household_context(session, character)
    if not house:
        raise HTTPException(404, "Владение не найдено.")
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
    members, member_ids, _, _ = await household_context(session, character)
    result = await session.execute(
        select(NpcUnit)
        .where(NpcUnit.character_id.in_(member_ids))
        .order_by(NpcUnit.alive.desc(), NpcUnit.npc_type, NpcUnit.id)
    )
    units = list(result.scalars())
    collected = await household_materials(session, member_ids)
    owner_names = {member.id: member.name for member in members}
    festival_active = local_date() <= "2026-08-25"
    spouse = next((member for member in members if member.id != character.id), None)
    return {
        "prices": {"guard": 80, "peasant": 70},
        "shared_with": spouse.name if spouse else None,
        "festival": {
            "active": festival_active,
            "ends_at": "25.08.2026",
            "claimed": bool(character.summer_guard_claimed),
            "can_claim": festival_active and not character.summer_guard_claimed,
        },
        "units": [
            await npc_payload(unit, collected, owner_names.get(unit.character_id))
            for unit in units
        ],
        "rules": {
            "guard_time": "Улучшенный стражник сильнее защищает совместный дом.",
            "fatigue": "При усталости 100 фермер нуждается в отдыхе. Без отдыха он может погибнуть.",
            "school": "Для каждого улучшения нужен новый комплект из 5 предметов. После улучшения предметы списываются. Первое стоит 25 монет, каждое следующее на 15 дороже.",
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
    try:
        await change_gold(session, character, -price, f"buy_npc:{payload.npc_type}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    count = await session.scalar(
        select(func.count(NpcUnit.id)).where(
            NpcUnit.character_id == character.id,
            NpcUnit.npc_type == payload.npc_type,
        )
    )
    index = int(count or 0) + 1
    unit = NpcUnit(
        character_id=character.id,
        npc_type=payload.npc_type,
        name=("Стражник" if payload.npc_type == "guard" else "Фермер") + f" №{index}",
        model_variant=1 if payload.npc_type == "guard" else ((index - 1) % 3) + 1,
    )
    session.add(unit)
    await session.flush()
    return {"ok": True, "unit": await npc_payload(unit), "gold": character.gold}


@router.post("/festival/summer-guard")
async def claim_summer_guard(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    if local_date() > "2026-08-25":
        raise HTTPException(400, "Летний фестиваль завершён 25 августа.")
    if character.summer_guard_claimed:
        raise HTTPException(400, "Фестивальный стражник уже получен.")
    count = await session.scalar(
        select(func.count(NpcUnit.id)).where(
            NpcUnit.character_id == character.id,
            NpcUnit.npc_type == "guard",
        )
    )
    index = int(count or 0) + 1
    unit = NpcUnit(
        character_id=character.id,
        npc_type="guard",
        name=f"Летний стражник №{index}",
        model_variant=1,
    )
    session.add(unit)
    character.summer_guard_claimed = True
    await session.flush()
    return {"ok": True, "message": "Летний стражник бесплатно добавлен во владение."}


@router.post("/npcs/upgrade")
async def upgrade_npc_unit(
    payload: NpcUpgradeRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    members, member_ids, _, _ = await household_context(session, character)
    npc = await session.get(NpcUnit, payload.npc_id)
    if not npc or npc.character_id not in member_ids or not npc.alive:
        raise HTTPException(404, "NPC не найден.")
    collected = await household_materials(session, member_ids)
    required = npc_upgrade_requirements(npc.npc_type)
    missing = [slug for slug in required if slug not in collected]
    if missing:
        raise HTTPException(400, "Сначала соберите полный комплект из 5 предметов в Магазине дня.")
    cost = 25 + npc.upgrade_count * 15
    try:
        await change_gold(session, character, -cost, f"npc_upgrade:{npc.npc_type}:{npc.id}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await consume_household_upgrade_materials(session, member_ids, required)
    npc.upgrade_count += 1
    npc.level += 1
    if npc.npc_type == "guard":
        npc.model_variant = guard_model_variant(npc.level)
    npc.fatigue = max(0, npc.fatigue - 10)
    remaining_materials = await household_materials(session, member_ids)
    owner_name = next((member.name for member in members if member.id == npc.character_id), None)
    return {
        "ok": True,
        "message": f"{npc.name} улучшен до уровня {npc.level} за {cost} монет. Комплект предметов использован.",
        "unit": await npc_payload(npc, remaining_materials, owner_name),
        "gold": character.gold,
    }


@router.post("/npcs/action")
async def npc_action(
    payload: NpcActionRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    members, member_ids, _, house = await household_context(session, character)
    npc = await session.get(NpcUnit, payload.npc_id)
    if not npc or npc.character_id not in member_ids or not npc.alive:
        raise HTTPException(404, "NPC не найден.")

    now = datetime.now(timezone.utc)
    available_at = npc.available_at
    if available_at and available_at.tzinfo is None:
        available_at = available_at.replace(tzinfo=timezone.utc)
    if available_at and available_at > now:
        raise HTTPException(400, "NPC сейчас занят.")
    if available_at and available_at <= now:
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
        try:
            await change_gold(session, character, -10, "guard_school")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        npc.status = "training"
        npc.assignment = "school"
        npc.available_at = now + timedelta(hours=4)
        return {"ok": True, "message": "Стражник отправлен в Королевскую школу на 4 часа."}

    if npc.fatigue >= 90:
        raise HTTPException(400, "Фермер слишком устал. Сначала отправьте его отдыхать.")

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
        reward = randint(4, 8) + npc.level * 2 + npc.upgrade_count * 2
        await change_gold(session, character, reward, "farmer_field")
        message = f"{label}: получено {reward} золота в общий бюджет."
    elif action == "clean":
        if house:
            house.cleanliness = 100
            house.last_cleaning_date = local_date()
        message = "Совместное владение убрано."
    elif action == "garden":
        if house:
            house.repair_energy += 3 + npc.level + npc.upgrade_count
        message = "Сад полит, получена энергия ремонта."
    else:
        character.experience += 4 + npc.upgrade_count
        apply_levels(character)
        message = "Туалеты очищены. Получен опыт."

    if npc.fatigue >= 100 and randint(1, 100) <= 35:
        npc.alive = False
        npc.status = "dead"
        message += " NPC погиб от истощения."
    collected = await household_materials(session, member_ids)
    owner_name = next((member.name for member in members if member.id == npc.character_id), None)
    return {"ok": True, "message": message, "unit": await npc_payload(npc, collected, owner_name)}


@router.post("/estate/repair")
async def repair_estate(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    _, _, _, house = await household_context(session, character)
    if not house:
        raise HTTPException(404, "Владение не найдено.")
    if house.integrity >= 100:
        raise HTTPException(400, "Владение уже полностью восстановлено.")
    cost = 15
    try:
        await change_gold(session, character, -cost, "estate_repair")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    restored = min(15, 100 - house.integrity)
    house.integrity += restored
    return {"ok": True, "cost": cost, "restored": restored, "integrity": house.integrity, "gold": character.gold}


async def registered_players_payload(session: AsyncSession, me: Character) -> list[dict]:
    result = await session.execute(
        select(Character, User)
        .join(User, User.id == Character.user_id)
        .order_by(Character.level.desc(), Character.name, Character.id)
    )
    rows = list(result.all())
    characters = {character.id: character for character, _ in rows}
    houses_result = await session.execute(select(House).order_by(House.owner_id))
    houses_by_owner = {house.owner_id: house for house in houses_result.scalars()}
    rooms_result = await session.execute(select(HouseRoom).order_by(HouseRoom.id))
    rooms_by_house: dict[int, list[HouseRoom]] = {}
    for room in rooms_result.scalars():
        rooms_by_house.setdefault(room.house_id, []).append(room)

    players = []
    for character, db_user in rows:
        spouse = characters.get(character.spouse_character_id) if character.spouse_character_id else None
        if spouse and spouse.spouse_character_id != character.id:
            spouse = None
        member_ids = [character.id] + ([spouse.id] if spouse else [])
        primary_id = min(member_ids)
        house = houses_by_owner.get(primary_id) or next(
            (houses_by_owner.get(member_id) for member_id in member_ids if houses_by_owner.get(member_id)),
            None,
        )
        household_house_ids = [
            houses_by_owner[member_id].id for member_id in member_ids if member_id in houses_by_owner
        ]
        rooms = [room for house_id in household_house_ids for room in rooms_by_house.get(house_id, [])]
        players.append({
            "id": character.id,
            "telegram_id": db_user.telegram_id,
            "name": character.name,
            "level": character.level,
            "is_me": character.id == me.id,
            "title": character.title,
            "faction": normalize_faction(character.faction),
            "social_status": character.social_status,
            "reputation": character.reputation,
            "portrait_available": bool(character.portrait_file_id),
            "spouse": ({"id": spouse.id, "name": spouse.name} if spouse else None),
            "house": ({
                "id": house.id,
                "name": house.name,
                "location": house.location,
                "description": house.description,
                "level": house.level,
                "integrity": house.integrity,
                "cleanliness": house.cleanliness,
                "shared": bool(spouse),
                "image_available": bool(house.image_file_id),
                "rooms": [{
                    "id": room.id,
                    "name": room.name,
                    "description": room.description,
                    "cleanliness": room.cleanliness,
                    "image_available": bool(room.image_file_id),
                } for room in rooms],
            } if house else None),
        })
    return players


@router.get("/friends")
async def friends_list(user=Depends(current_miniapp_user), session: AsyncSession=Depends(get_session)):
    me = await require_character(user, session)
    players = await registered_players_payload(session, me)
    return {"players": players, "count": len(players)}


@router.get("/friends/{character_id}/portrait")
async def friend_portrait(character_id: int, user=Depends(current_miniapp_user), session: AsyncSession=Depends(get_session)):
    await require_character(user, session)
    file_id = await session.scalar(select(Character.portrait_file_id).where(Character.id == character_id))
    if not file_id:
        raise HTTPException(404, "Портрет не найден.")
    return await telegram_file_response(file_id)


@router.get("/friends/{character_id}/house-image")
async def friend_house_image(character_id: int, user=Depends(current_miniapp_user), session: AsyncSession=Depends(get_session)):
    await require_character(user, session)
    target = await session.get(Character, character_id)
    if not target:
        raise HTTPException(404, "Игрок не найден.")
    _, _, _, house = await household_context(session, target)
    if not house or not house.image_file_id:
        raise HTTPException(404, "Изображение владения не найдено.")
    return await telegram_file_response(house.image_file_id)


@router.get("/friends/{character_id}/rooms/{room_id}/image")
async def friend_room_image(
    character_id: int,
    room_id: int,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    await require_character(user, session)
    target = await session.get(Character, character_id)
    if not target:
        raise HTTPException(404, "Игрок не найден.")
    _, _, houses, _ = await household_context(session, target)
    room = await session.get(HouseRoom, room_id)
    if not room or room.house_id not in {house.id for house in houses} or not room.image_file_id:
        raise HTTPException(404, "Изображение комнаты не найдено.")
    return await telegram_file_response(room.image_file_id)


@router.post("/friends/{character_id}/repair")
async def repair_friend_house(
    character_id: int,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    helper = await require_character(user, session)
    target = await session.get(Character, character_id)
    if not target:
        raise HTTPException(404, "Игрок не найден.")
    target_members, _, _, house = await household_context(session, target)
    if helper.id in {member.id for member in target_members}:
        raise HTTPException(400, "Свой совместный дом ремонтируется в разделе Владение.")
    if not house:
        raise HTTPException(404, "Владение игрока не найдено.")
    if house.integrity >= 100:
        raise HTTPException(400, "Дом уже полностью восстановлен.")
    cost = 12
    try:
        await change_gold(session, helper, -cost, f"friend_house_repair:{target.id}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    restored = min(12, 100 - house.integrity)
    house.integrity += restored
    return {
        "ok": True,
        "cost": cost,
        "restored": restored,
        "integrity": house.integrity,
        "message": f"Вы помогли восстановить дом игрока {target.name} на {restored} прочности.",
    }


@router.get("/statistics")
async def player_statistics(user=Depends(current_miniapp_user), session: AsyncSession=Depends(get_session)):
    character = await require_character(user, session)
    _, member_ids, houses, house = await household_context(session, character)
    house_ids = [item.id for item in houses]
    tarot_count = await session.scalar(select(func.count(TarotReading.id)).where(TarotReading.character_id == character.id))
    room_count = await session.scalar(select(func.count(HouseRoom.id)).where(HouseRoom.house_id.in_(house_ids))) if house_ids else 0
    npc_count = await session.scalar(select(func.count(NpcUnit.id)).where(NpcUnit.character_id.in_(member_ids), NpcUnit.alive.is_(True)))
    attack_wins = await session.scalar(select(func.count(HouseAttack.id)).where(
        HouseAttack.house_id == house.id,
        HouseAttack.status.in_(["owner_won", "guards_won"]),
    )) if house else 0
    attacks_total = await session.scalar(select(func.count(HouseAttack.id)).where(HouseAttack.house_id == house.id)) if house else 0
    return {
        "duel_wins": character.duel_wins, "duel_losses": character.duel_losses,
        "duel_rating": character.duel_rating, "win_streak": character.duel_win_streak,
        "tarot_readings": int(tarot_count or 0), "rooms": int(room_count or 0),
        "npcs": int(npc_count or 0), "house_defenses_won": int(attack_wins or 0),
        "house_attacks": int(attacks_total or 0), "level": character.level,
        "reputation": character.reputation, "gold": character.gold,
    }


@router.post("/presence")
async def update_presence(
    payload: PresenceRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    db_user = await database_user(session, user.id)
    if not db_user:
        raise HTTPException(404, "Игрок не найден.")
    db_user.current_view = payload.view
    db_user.last_seen_at = datetime.now(timezone.utc)
    return {"ok": True}


def presence_payload(db_user: User) -> dict[str, object]:
    last_seen = db_user.last_seen_at
    if last_seen and last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    online = bool(last_seen and datetime.now(timezone.utc) - last_seen <= timedelta(minutes=5))
    view_key = db_user.current_view or "home"
    return {
        "view": view_key,
        "view_label": VIEW_LABELS.get(view_key, view_key),
        "online": online,
        "last_seen": last_seen.isoformat() if last_seen else None,
    }


@router.get("/admin/players")
async def admin_players(user=Depends(current_miniapp_user), session: AsyncSession=Depends(get_session)):
    await require_project_admin(session, user.id)
    result = await session.execute(
        select(Character)
        .options(selectinload(Character.user), selectinload(Character.house))
        .order_by(Character.name)
    )
    characters = list(result.scalars())
    names = {character.id: character.name for character in characters}
    return {
        "allowed_titles": list(TITLES),
        "factions": list(FACTIONS),
        "players": [{
            "id": c.id,
            "telegram_id": c.user.telegram_id,
            "name": c.name,
            "level": c.level,
            "title": c.title,
            "social_status": c.social_status,
            "faction": normalize_faction(c.faction),
            "spouse_character_id": c.spouse_character_id,
            "spouse_name": names.get(c.spouse_character_id),
            "activity": presence_payload(c.user),
        } for c in characters]
    }


@router.post("/admin/players/title")
async def admin_set_player_title(payload: PlayerTitleRequest, user=Depends(current_miniapp_user), session: AsyncSession=Depends(get_session)):
    await require_project_admin(session, user.id)
    character = await session.get(Character, payload.character_id)
    if not character:
        raise HTTPException(404, "Игрок не найден.")
    title = payload.title.strip()
    if title not in TITLES:
        raise HTTPException(400, "Разрешены титулы: " + ", ".join(TITLES))
    character.title = title
    return {"ok": True, "id": character.id, "title": character.title}


async def clear_marriage(session: AsyncSession, character: Character) -> None:
    spouse = await session.get(Character, character.spouse_character_id) if character.spouse_character_id else None
    if spouse and spouse.spouse_character_id == character.id:
        shared_balance = max(character.gold, spouse.gold)
        character.gold = shared_balance // 2 + shared_balance % 2
        spouse.gold = shared_balance // 2
        spouse.spouse_character_id = None
        spouse.social_status = "Не в браке"
    character.spouse_character_id = None
    character.social_status = "Не в браке"


@router.post("/admin/players/marriage")
async def admin_set_marriage(
    payload: PlayerMarriageRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    await require_project_admin(session, user.id)
    character = await session.get(Character, payload.character_id)
    if not character:
        raise HTTPException(404, "Игрок не найден.")
    if payload.spouse_character_id is None:
        await clear_marriage(session, character)
        return {"ok": True, "character_id": character.id, "spouse_character_id": None}
    if payload.spouse_character_id == character.id:
        raise HTTPException(400, "Нельзя назначить брак с самим собой.")
    spouse = await session.get(Character, payload.spouse_character_id)
    if not spouse:
        raise HTTPException(404, "Второй игрок не найден.")
    if character.spouse_character_id and character.spouse_character_id != spouse.id:
        raise HTTPException(400, "Сначала снимите текущий статус брака у первого игрока.")
    if spouse.spouse_character_id and spouse.spouse_character_id != character.id:
        raise HTTPException(400, "Второй игрок уже состоит в браке.")
    shared_balance = character.gold + spouse.gold if character.spouse_character_id != spouse.id else max(character.gold, spouse.gold)
    character.gold = shared_balance
    spouse.gold = shared_balance
    character.spouse_character_id = spouse.id
    spouse.spouse_character_id = character.id
    character.social_status = "В браке"
    spouse.social_status = "В браке"
    return {
        "ok": True,
        "character_id": character.id,
        "spouse_character_id": spouse.id,
        "shared_gold": shared_balance,
    }

