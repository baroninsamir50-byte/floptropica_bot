from random import randint, choice, sample
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
    SystemMedia, TarotCard, TarotReading, House, HouseAttack, HouseRoom, NpcUnit, PlayerStory, StoryRead,
    Farm, FarmPlot, FarmStock, FarmMarketListing, EstateEventCycle,
)
from app.miniapp.auth import TelegramMiniAppUser, current_miniapp_user
from app.services import (
    buy_item, claim_work, get_character, get_daily_shop_items,
    get_equipment_bonuses, get_system_media, local_date,
    start_work, toggle_equip, xp_for_next, claim_daily_reward,
    level_income_multiplier, level_rank, set_system_media, change_gold, apply_levels,
    get_effective_stats, household_members, GUARD_UPGRADE_ITEMS,
    FARMER_UPGRADE_ITEMS, NPC_UPGRADE_ITEMS, WORK_REWARD_MULTIPLIER,
    guard_model_variant, npc_model_variant, npc_upgrade_plan, npc_stat_gains, npc_power,
    grant_inventory_item,
)
from app.work_catalog import available_professions, profession_by_key, title_can_use, profession_income_multiplier
from app.miniapp.duel_engine import STYLES, initialize_duel, perform_action, log_list
from app.tarot_service import create_daily_reading, offered_cards
from app.farm_events import (
    CROPS, FARM_PRICE, FARMER_PRICE, FARM_START_PLOTS, FARM_BARN_CAPACITY, MARKET_COMMISSION,
    ESTATE_EVENTS, EVENT_BY_ID, CATEGORY_LABELS, json_list, json_dict,
    event_options, event_payload,
)
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
class UseInventoryRequest(BaseModel):
    inventory_id: int
class DuelChallengeRequest(BaseModel):
    opponent_id: int
    style: str = "guardian"

class DuelAcceptRequest(BaseModel):
    style: str = "guardian"

class DuelActionRequest(BaseModel):
    action: Literal["attack","magic","defend","dodge","critical","potion"]

class FarmPlantRequest(BaseModel):
    plot_id: int
    crop_slug: str = Field(min_length=1, max_length=40)

class FarmPlotRequest(BaseModel):
    plot_id: int

class FarmAssignRequest(BaseModel):
    npc_id: int | None = None

class FarmFeedRequest(BaseModel):
    npc_id: int
    crop_slug: str = Field(min_length=1, max_length=40)

class FarmAutoFeedRequest(BaseModel):
    enabled: bool

class FarmListingRequest(BaseModel):
    crop_slug: str = Field(min_length=1, max_length=40)
    quantity: int = Field(ge=1, le=99)
    unit_price: int = Field(ge=1, le=999)

class FarmBuyListingRequest(BaseModel):
    listing_id: int

class EstateEventChooseRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=40)


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


def event_result_payload(cycle: EstateEventCycle | None) -> dict[str, object] | None:
    if not cycle or cycle.result_event_id not in EVENT_BY_ID:
        return None
    event = event_payload(str(cycle.result_event_id))
    kind_labels = {
        "success": "СОБЫТИЕ ПРЕДОТВРАЩЕНО",
        "partial": "УГРОЗА ЧАСТИЧНО ПРЕДОТВРАЩЕНА",
        "critical": "СОБЫТИЕ АКТИВИРОВАЛОСЬ",
    }
    return {
        "cycle_id": cycle.id,
        "kind": cycle.result_kind,
        "kind_label": kind_labels.get(str(cycle.result_kind), "ИТОГ ЦИКЛА"),
        "event": event,
        "text": cycle.result_text or "",
        "matched_count": cycle.matched_count,
        "reward_gold": cycle.reward_gold,
        "reward_item_slug": cycle.reward_item_slug,
    }


@router.get("/bootstrap")
async def bootstrap(user: TelegramMiniAppUser=Depends(current_miniapp_user), session: AsyncSession=Depends(get_session)):
    c = await require_character(user, session)
    c.faction = normalize_faction(c.faction)
    if c.work_count_date != local_date():
        c.work_count_date = local_date()
        c.work_count = 0
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
        "inventory_id":inv.id,"item_id":item.id,"slug":item.slug,"name":item.name,"description":item.description,
        "quantity":inv.quantity,"equipped":inv.equipped,"slot":item.slot,"rarity":item.rarity,
        "stat_name":item.stat_name,"stat_bonus":item.stat_bonus,
    } for inv,item in inv_result.all()]
    npc_result=await session.execute(select(OwnedNpc).where(OwnedNpc.character_id==c.id))
    npcs={n.npc_type:n.quantity for n in npc_result.scalars()}
    media_keys=("home_bg","hero_bg","house_bg","treasury","shop","development","factions","map","games_bg","inventory_bg","loading_bg","app_logo","topbar_bg","nav_bg","card_texture","frame_hero","frame_house","icon_hero","icon_house","icon_treasury","icon_shop","icon_map","icon_games","icon_factions","icon_inventory","icon_development","icon_daily","duel_bg","duel_frame","duel_vs","icon_customization","tarot_bg","tarot_back","icon_tarot","npc_bg","icon_npc","room_bg","farm_bg","icon_farm","enemy_dragon_1","enemy_dragon_2","enemy_dragon_3","enemy_monster_1","enemy_monster_2","enemy_monster_3","enemy_anomaly_1","enemy_anomaly_2","enemy_anomaly_3","guard_model_1","guard_model_2","guard_model_3","peasant_model_1","peasant_model_2","peasant_model_3","npc_peasant_1","npc_peasant_2","npc_peasant_3","npc_farmer_1","npc_farmer_2","npc_farmer_3","npc_gardener_1","npc_gardener_2","npc_gardener_3","npc_forester_1","npc_forester_2","npc_forester_3","npc_miner_1","npc_miner_2","npc_miner_3","npc_fisher_1","npc_fisher_2","npc_fisher_3","npc_cook_1","npc_cook_2","npc_cook_3","npc_recruit_1","npc_recruit_2","npc_recruit_3","npc_guard_1","npc_guard_2","npc_guard_3","npc_veteran_1","npc_veteran_2","npc_veteran_3","npc_archer_1","npc_archer_2","npc_archer_3","npc_rider_1","npc_rider_2","npc_rider_3","npc_paladin_1","npc_paladin_2","npc_paladin_3","npc_dragon_tamer_1","npc_dragon_tamer_2","npc_dragon_tamer_3","npc_mage_1","npc_mage_2","npc_mage_3","npc_seer_1","npc_seer_2","npc_seer_3","npc_alchemist_1","npc_alchemist_2","npc_alchemist_3","npc_exorcist_1","npc_exorcist_2","npc_exorcist_3","npc_archmage_1","npc_archmage_2","npc_archmage_3","npc_merchant_1","npc_merchant_2","npc_merchant_3","npc_banker_1","npc_banker_2","npc_banker_3","npc_quartermaster_1","npc_quartermaster_2","npc_quartermaster_3","npc_treasurer_1","npc_treasurer_2","npc_treasurer_3","npc_judge_1","npc_judge_2","npc_judge_3","npc_scribe_1","npc_scribe_2","npc_scribe_3","npc_advisor_1","npc_advisor_2","npc_advisor_3","npc_chancellor_1","npc_chancellor_2","npc_chancellor_3","npc_bard_1","npc_bard_2","npc_bard_3","npc_artist_1","npc_artist_2","npc_artist_3","npc_librarian_1","npc_librarian_2","npc_librarian_3","npc_architect_1","npc_architect_2","npc_architect_3","npc_dog_1","npc_dog_2","npc_dog_3","npc_cat_1","npc_cat_2","npc_cat_3","npc_falcon_1","npc_falcon_2","npc_falcon_3","npc_small_dragon_1","npc_small_dragon_2","npc_small_dragon_3","npc_royal_architect_1","npc_royal_architect_2","npc_royal_architect_3","npc_great_magister_1","npc_great_magister_2","npc_great_magister_3","npc_royal_general_1","npc_royal_general_2","npc_royal_general_3","npc_forest_keeper_1","npc_forest_keeper_2","npc_forest_keeper_3","npc_angel_of_light_1","npc_angel_of_light_2","npc_angel_of_light_3") + tuple(f"event_card_{number}" for number in range(1, 21))
    media={k:(f"/api/miniapp/media/{k}" if await get_system_media(session,k) else None) for k in media_keys}
    remaining=0
    if c.work_ends_at and not c.work_reward_claimed:
        remaining=max(0,int((c.work_ends_at-datetime.now(timezone.utc)).total_seconds()))
    bot_username = await get_bot_username()
    pending_cycle = await session.scalar(
        select(EstateEventCycle).where(
            EstateEventCycle.character_id == c.id,
            EstateEventCycle.status == "resolved",
            EstateEventCycle.result_acknowledged.is_(False),
        ).order_by(EstateEventCycle.id.desc())
    )
    pending_event_result = event_result_payload(pending_cycle) if pending_cycle else None
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
            "gold":[max(1, int(d["gold"][0] * level_income_multiplier(c.level) * WORK_REWARD_MULTIPLIER * profession_income_multiplier(c.title, d))), max(1, int(d["gold"][1] * level_income_multiplier(c.level) * WORK_REWARD_MULTIPLIER * profession_income_multiplier(c.title, d)))],
            "xp":list(d["xp"]), "role_bonus": round(profession_income_multiplier(c.title, d)-1.0, 2)} for k,d in available_professions(c.title)],
        "shop":{"date":local_date(),"items":[{"id":i.id,"name":i.name,"description":i.description,"price":i.price,
            "slot":i.slot,"rarity":i.rarity,"stat_name":i.stat_name,"stat_bonus":i.stat_bonus} for i in shop]},
        "inventory":inventory,"npcs":npcs,"media":media,
        "pending_event_result": pending_event_result,
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
        gold,xp,title_reward=await claim_work(session,c); return {"ok":True,"gold":gold,"xp":xp,"title_reward":title_reward}
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
        "tarot_bg","tarot_back","icon_tarot","npc_bg","icon_npc","room_bg","farm_bg","icon_farm",
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
    allowed.update({f"event_card_{number}" for number in range(1, 21)})
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
    "tarot_bg","tarot_back","icon_tarot","npc_bg","icon_npc","room_bg","farm_bg","icon_farm",
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
THEME_KEYS.update({f"event_card_{number}" for number in range(1, 21)})

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

@router.post("/inventory/use")
async def use_inventory_item(payload: UseInventoryRequest, user=Depends(current_miniapp_user), session:AsyncSession=Depends(get_session)):
    character = await require_character(user, session)
    result = await session.execute(
        select(InventoryItem, ItemTemplate)
        .join(ItemTemplate, ItemTemplate.id == InventoryItem.item_id)
        .where(InventoryItem.id == payload.inventory_id, InventoryItem.character_id == character.id)
    )
    row = result.first()
    if not row:
        raise HTTPException(404, "Предмет не найден.")
    inventory_item, item = row
    if item.slug not in {"healing_potion", "greater_healing_potion"}:
        raise HTTPException(400, "Этот предмет нельзя использовать таким способом.")
    restored = int(item.stat_bonus or 10)
    character.health += restored
    if inventory_item.quantity <= 1:
        await session.delete(inventory_item)
    else:
        inventory_item.quantity -= 1
    return {"ok": True, "message": f"{item.name} использовано: здоровье героя увеличено на {restored}.", "health": character.health}


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


def settle_npc_state(npc: NpcUnit, now: datetime | None = None) -> None:
    """Завершает отдых/занятие и применяет мягкое правило смерти только после 24 часов игнорирования."""
    now = now or datetime.now(timezone.utc)
    available_at = _aware(npc.available_at)
    if available_at and available_at <= now:
        if npc.status == "resting":
            recovery = 60 if npc.assignment == "rest_long" else 35
            npc.fatigue = max(0, int(npc.fatigue or 0) - recovery)
            npc.exhaustion_started_at = None
        elif npc.status == "training":
            npc.experience += 20
            npc.skill += 2
            npc.endurance += 1
        npc.status = "idle"
        npc.assignment = None
        npc.available_at = None
    sync_npc_vitals(npc, now)
    if not npc.alive:
        return
    starvation = _aware(npc.starvation_started_at)
    exhaustion = _aware(npc.exhaustion_started_at)
    starving_too_long = bool(npc.hunger >= 100 and starvation and now - starvation >= timedelta(hours=24))
    exhausted_too_long = bool(
        npc.status != "resting" and npc.fatigue >= 100 and exhaustion
        and now - exhaustion >= timedelta(hours=24)
    )
    if starving_too_long or exhausted_too_long:
        npc.alive = False
        npc.status = "dead"
        npc.assignment = "starvation" if starving_too_long else "exhaustion"
        npc.available_at = None


async def npc_payload(
    npc: NpcUnit,
    collected_slugs: set[str] | None = None,
    owner_name: str | None = None,
) -> dict:
    settle_npc_state(npc)
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
    plan = npc_upgrade_plan(npc.level)
    upgrade_cost = int(plan["cost"])
    requires_kit = bool(plan["requires_kit"])
    model_variant = npc_model_variant(npc.level)
    if npc.model_variant != model_variant:
        npc.model_variant = model_variant
    stats = {
        "strength": npc.strength,
        "endurance": npc.endurance,
        "agility": npc.agility,
        "skill": npc.skill,
    }
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
        "upgrade_stage": plan["stage"],
        "requires_kit": requires_kit,
        "max_level": bool(plan["max_level"]),
        "next_level": min(npc.level + 1, 50),
        "upgrade_ready": (not requires_kit) or all(slug in collected_slugs for slug in required),
        "upgrade_materials": [
            {"slug": slug, "name": material_names[slug], "owned": slug in collected_slugs}
            for slug in required
        ],
        "experience": npc.experience,
        "stats": stats,
        "power": npc_power(npc),
        "fatigue": npc.fatigue,
        "hunger": npc.hunger,
        "condition": npc_condition(npc),
        "status": npc.status,
        "assignment": npc.assignment,
        "remaining_seconds": remaining,
        "alive": npc.alive,
        "model_url": f"/api/miniapp/media/{npc.npc_type}_model_{model_variant}"
            if npc.npc_type in {"guard", "peasant"} else None,
    }

def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def sync_npc_vitals(npc: NpcUnit, now: datetime | None = None) -> None:
    """Лениво обновляет голод и безопасные состояния NPC."""
    now = now or datetime.now(timezone.utc)
    updated = _aware(npc.hunger_updated_at) or now
    elapsed = max(0, int((now - updated).total_seconds()))
    hunger_points = elapsed // (3 * 60 * 60)
    if hunger_points:
        npc.hunger = min(100, int(npc.hunger or 0) + hunger_points)
        npc.hunger_updated_at = updated + timedelta(hours=hunger_points * 3)
    elif npc.hunger_updated_at is None:
        npc.hunger_updated_at = now

    if npc.hunger >= 100:
        npc.starvation_started_at = _aware(npc.starvation_started_at) or now
    else:
        npc.starvation_started_at = None
    if npc.fatigue >= 100:
        npc.exhaustion_started_at = _aware(npc.exhaustion_started_at) or now
    else:
        npc.exhaustion_started_at = None


def npc_condition(npc: NpcUnit) -> dict[str, object]:
    if not npc.alive:
        return {"label": "Погиб", "severity": "critical", "work_multiplier": 0.0}
    if npc.status == "resting":
        return {"label": "Отдыхает", "severity": "safe", "work_multiplier": 0.0}
    if npc.hunger >= 100 or npc.fatigue >= 100:
        return {"label": "Истощён", "severity": "critical", "work_multiplier": 0.0}
    if npc.hunger >= 90 or npc.fatigue >= 90:
        return {"label": "Не может работать", "severity": "danger", "work_multiplier": 0.0}
    if npc.hunger >= 70 or npc.fatigue >= 70:
        return {"label": "Ослаблен", "severity": "warning", "work_multiplier": 0.85}
    return {"label": "В норме", "severity": "normal", "work_multiplier": 1.0}


async def farm_for_house(session: AsyncSession, house_id: int) -> Farm | None:
    return await session.scalar(select(Farm).where(Farm.house_id == house_id))


async def ensure_free_farm(session: AsyncSession, house_id: int) -> Farm:
    """Возвращает ферму владения, бесплатно создавая стартовые 3 грядки."""
    farm = await farm_for_house(session, house_id)
    if farm:
        return farm
    farm = Farm(
        house_id=house_id,
        level=1,
        plot_count=FARM_START_PLOTS,
        barn_capacity=FARM_BARN_CAPACITY,
        auto_feed=True,
    )
    session.add(farm)
    await session.flush()
    for slot in range(1, FARM_START_PLOTS + 1):
        session.add(FarmPlot(farm_id=farm.id, slot=slot))
    await session.flush()
    return farm


async def stock_rows(session: AsyncSession, farm_id: int) -> list[FarmStock]:
    result = await session.execute(
        select(FarmStock).where(FarmStock.farm_id == farm_id).order_by(FarmStock.crop_slug)
    )
    return list(result.scalars())


async def barn_used(session: AsyncSession, farm_id: int) -> int:
    amount = await session.scalar(
        select(func.coalesce(func.sum(FarmStock.quantity), 0)).where(FarmStock.farm_id == farm_id)
    )
    return int(amount or 0)


async def add_crop_stock(session: AsyncSession, farm: Farm, crop_slug: str, quantity: int) -> int:
    used = await barn_used(session, farm.id)
    accepted = max(0, min(int(quantity), int(farm.barn_capacity) - used))
    if accepted <= 0:
        return 0
    row = await session.scalar(
        select(FarmStock).where(FarmStock.farm_id == farm.id, FarmStock.crop_slug == crop_slug)
    )
    if row:
        row.quantity += accepted
    else:
        session.add(FarmStock(farm_id=farm.id, crop_slug=crop_slug, quantity=accepted))
    return accepted


async def take_crop_stock(session: AsyncSession, farm: Farm, crop_slug: str, quantity: int) -> None:
    row = await session.scalar(
        select(FarmStock).where(FarmStock.farm_id == farm.id, FarmStock.crop_slug == crop_slug)
    )
    if not row or row.quantity < quantity:
        raise HTTPException(400, "В амбаре недостаточно урожая.")
    row.quantity -= quantity
    if row.quantity <= 0:
        await session.delete(row)


def clear_plot(plot: FarmPlot) -> None:
    plot.crop_slug = None
    plot.planted_at = None
    plot.water_due_at = None
    plot.watered_at = None
    plot.ready_at = None


async def sync_farm_automation(
    session: AsyncSession,
    farm: Farm,
    member_ids: list[int],
) -> None:
    """Фермер автоматически обслуживает две грядки; третья остаётся игроку."""
    if not farm.farmer_npc_id:
        return
    farmer = await session.get(NpcUnit, farm.farmer_npc_id)
    if not farmer or farmer.character_id not in member_ids or farmer.npc_type != "peasant" or not farmer.alive:
        farm.farmer_npc_id = None
        return
    settle_npc_state(farmer)
    condition = npc_condition(farmer)
    if condition["work_multiplier"] == 0 or farmer.status not in {"idle", "working"}:
        return
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(FarmPlot).where(FarmPlot.farm_id == farm.id).order_by(FarmPlot.slot)
    )
    active = [plot for plot in result.scalars() if plot.crop_slug]
    capacity = min(3, 2 + max(0, farmer.skill - 20) // 20)
    for plot in active[:capacity]:
        if farmer.fatigue >= 90 or farmer.hunger >= 90:
            break
        water_due = _aware(plot.water_due_at)
        ready_at = _aware(plot.ready_at)
        if not plot.watered_at and water_due and now >= water_due:
            plot.watered_at = now
            farmer.fatigue = min(100, farmer.fatigue + 4)
            farmer.hunger = min(100, farmer.hunger + 2)
            farmer.experience += 2
        if plot.watered_at and ready_at and now >= ready_at and plot.crop_slug in CROPS:
            crop = CROPS[plot.crop_slug]
            accepted = await add_crop_stock(session, farm, plot.crop_slug, int(crop["yield"]))
            if accepted <= 0:
                break
            clear_plot(plot)
            farmer.fatigue = min(100, farmer.fatigue + 6)
            farmer.hunger = min(100, farmer.hunger + 4)
            farmer.experience += 4 + farmer.level
    sync_npc_vitals(farmer, now)


async def auto_feed_household(
    session: AsyncSession,
    farm: Farm,
    member_ids: list[int],
) -> None:
    if not farm.auto_feed:
        return
    result = await session.execute(
        select(NpcUnit).where(
            NpcUnit.character_id.in_(member_ids),
            NpcUnit.alive.is_(True),
            NpcUnit.hunger >= 70,
        ).order_by(NpcUnit.hunger.desc())
    )
    npcs = list(result.scalars())
    if not npcs:
        return
    stocks = await stock_rows(session, farm.id)
    stock_map = {row.crop_slug: row for row in stocks if row.quantity > 0}
    crop_order = sorted(CROPS, key=lambda slug: int(CROPS[slug]["hunger_restore"]), reverse=True)
    for npc in npcs:
        sync_npc_vitals(npc)
        while npc.hunger >= 50:
            selected = next((slug for slug in crop_order if stock_map.get(slug) and stock_map[slug].quantity > 0), None)
            if not selected:
                break
            row = stock_map[selected]
            row.quantity -= 1
            npc.hunger = max(0, npc.hunger - int(CROPS[selected]["hunger_restore"]))
            npc.starvation_started_at = None
            if row.quantity <= 0:
                await session.delete(row)
                stock_map.pop(selected, None)


async def household_live_npcs(session: AsyncSession, member_ids: list[int]) -> list[NpcUnit]:
    result = await session.execute(
        select(NpcUnit).where(
            NpcUnit.character_id.in_(member_ids),
            NpcUnit.alive.is_(True),
        ).order_by(NpcUnit.npc_type, NpcUnit.name)
    )
    units = list(result.scalars())
    for unit in units:
        settle_npc_state(unit)
    return [unit for unit in units if unit.alive]


async def farm_payload(
    session: AsyncSession,
    farm: Farm,
    member_ids: list[int],
    members: list[Character],
) -> dict[str, object]:
    await sync_farm_automation(session, farm, member_ids)
    await auto_feed_household(session, farm, member_ids)
    plots_result = await session.execute(
        select(FarmPlot).where(FarmPlot.farm_id == farm.id).order_by(FarmPlot.slot)
    )
    plots = list(plots_result.scalars())
    stocks = await stock_rows(session, farm.id)
    farmer = await session.get(NpcUnit, farm.farmer_npc_id) if farm.farmer_npc_id else None
    now = datetime.now(timezone.utc)
    manageable = set()
    if farmer:
        manageable = {plot.id for plot in [p for p in plots if p.crop_slug][:min(3, 2 + max(0, farmer.skill - 20) // 20)]}
    plot_payloads = []
    for plot in plots:
        crop = CROPS.get(plot.crop_slug or "")
        ready_at = _aware(plot.ready_at)
        water_due = _aware(plot.water_due_at)
        remaining = max(0, int((ready_at - now).total_seconds())) if ready_at else 0
        if not crop:
            stage = "empty"
        elif ready_at and now >= ready_at and plot.watered_at:
            stage = "ready"
        elif not plot.watered_at and water_due and now >= water_due:
            stage = "needs_water"
        elif plot.watered_at:
            stage = "growing"
        else:
            stage = "sprout"
        plot_payloads.append({
            "id": plot.id, "slot": plot.slot, "crop_slug": plot.crop_slug,
            "crop": ({**crop, "slug": plot.crop_slug} if crop else None),
            "stage": stage, "remaining_seconds": remaining,
            "watered": bool(plot.watered_at), "auto_managed": plot.id in manageable,
        })
    peasant_result = await session.execute(
        select(NpcUnit).where(
            NpcUnit.character_id.in_(member_ids), NpcUnit.npc_type == "peasant", NpcUnit.alive.is_(True)
        ).order_by(NpcUnit.level.desc(), NpcUnit.id)
    )
    farmers = list(peasant_result.scalars())
    all_npcs_result = await session.execute(
        select(NpcUnit).where(
            NpcUnit.character_id.in_(member_ids), NpcUnit.alive.is_(True)
        ).order_by(NpcUnit.npc_type, NpcUnit.level.desc(), NpcUnit.id)
    )
    all_npcs = list(all_npcs_result.scalars())
    for npc in all_npcs:
        sync_npc_vitals(npc, now)
    owner_names = {member.id: member.name for member in members}
    return {
        "built": True,
        "price": FARM_PRICE,
        "farmer_price": FARMER_PRICE,
        "farm": {
            "id": farm.id, "level": farm.level, "plot_count": farm.plot_count,
            "barn_capacity": farm.barn_capacity, "barn_used": sum(row.quantity for row in stocks),
            "auto_feed": farm.auto_feed,
            "farmer_npc_id": farm.farmer_npc_id,
        },
        "plots": plot_payloads,
        "stock": [{
            "crop_slug": row.crop_slug, "quantity": row.quantity,
            "crop": {**CROPS[row.crop_slug], "slug": row.crop_slug},
        } for row in stocks if row.crop_slug in CROPS and row.quantity > 0],
        "crops": [{**data, "slug": slug} for slug, data in CROPS.items()],
        "farmers": [{
            "id": npc.id, "name": npc.name, "level": npc.level,
            "fatigue": npc.fatigue, "hunger": npc.hunger,
            "owner_name": owner_names.get(npc.character_id),
            "condition": npc_condition(npc),
        } for npc in farmers],
        "assigned_farmer": ({
            "id": farmer.id, "name": farmer.name, "level": farmer.level,
            "fatigue": farmer.fatigue, "hunger": farmer.hunger,
            "condition": npc_condition(farmer),
        } if farmer else None),
        "npcs": [
            {"id": npc.id, "name": npc.name, "type": npc.npc_type, "hunger": npc.hunger, "fatigue": npc.fatigue}
            for npc in await household_live_npcs(session, member_ids)
        ],
        "visual_assets": {
            "kenney_scene": "https://opengameart.org/sites/default/files/styles/medium/public/sample_95.png",
            "kenney_preview": "https://opengameart.org/sites/default/files/styles/medium/public/preview_1116.png",
            "medieval_tiles": "https://opengameart.org/sites/default/files/medieval%20tileset%20exterior.png",
            "farm_props": "https://lpc.opengameart.org/sites/default/files/styles/medium/public/tileset_preview.png",
        },
    }


@router.get("/farm")
async def farm_center(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    members, member_ids, _, house = await household_context(session, character)
    if not house:
        raise HTTPException(404, "Сначала создайте владение.")
    # Ферма является бесплатной частью владения. При первом входе создаём
    # стартовые три грядки и амбар без списания монет.
    farm = await ensure_free_farm(session, house.id)
    payload = await farm_payload(session, farm, member_ids, members)
    payload["tutorial_required"] = not character.farm_tutorial_completed
    listings_result = await session.execute(
        select(FarmMarketListing, Character)
        .join(Character, Character.id == FarmMarketListing.seller_character_id)
        .where(FarmMarketListing.status == "active", FarmMarketListing.expires_at > datetime.now(timezone.utc))
        .order_by(FarmMarketListing.created_at.desc())
    )
    payload["market"] = [{
        "id": listing.id, "crop_slug": listing.crop_slug,
        "crop": {**CROPS[listing.crop_slug], "slug": listing.crop_slug},
        "quantity": listing.quantity, "unit_price": listing.unit_price,
        "total_price": listing.quantity * listing.unit_price,
        "seller_id": seller.id, "seller_name": seller.name,
        "is_mine": seller.id == character.id,
    } for listing, seller in listings_result.all() if listing.crop_slug in CROPS]
    return payload


@router.post("/farm/build")
async def build_farm(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    """Совместимость со старым интерфейсом: ферма открывается бесплатно."""
    character = await require_character(user, session)
    _, _, _, house = await household_context(session, character)
    if not house:
        raise HTTPException(404, "Сначала создайте владение.")
    await ensure_free_farm(session, house.id)
    return {
        "ok": True,
        "message": "Ферма открыта бесплатно. Доступны 3 грядки; до найма фермера вы ухаживаете за ними сами.",
        "gold": character.gold,
    }


@router.post("/farm/plant")
async def plant_crop(
    payload: FarmPlantRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    _, _, _, house = await household_context(session, character)
    farm = await farm_for_house(session, house.id) if house else None
    if not farm:
        raise HTTPException(404, "Откройте раздел фермы во владении.")
    crop = CROPS.get(payload.crop_slug)
    if not crop:
        raise HTTPException(404, "Культура не найдена.")
    plot = await session.get(FarmPlot, payload.plot_id)
    if not plot or plot.farm_id != farm.id:
        raise HTTPException(404, "Грядка не найдена.")
    if plot.crop_slug:
        raise HTTPException(400, "Грядка уже занята.")
    try:
        await change_gold(session, character, -int(crop["seed_price"]), f"farm_seed:{payload.crop_slug}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    now = datetime.now(timezone.utc)
    growth = timedelta(hours=int(crop["growth_hours"]))
    plot.crop_slug = payload.crop_slug
    plot.planted_at = now
    plot.water_due_at = now + growth * 0.35
    plot.watered_at = None
    plot.ready_at = now + growth
    return {"ok": True, "message": f"Посажено: {crop['name']}.", "gold": character.gold}


@router.post("/farm/water")
async def water_plot(
    payload: FarmPlotRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    _, _, _, house = await household_context(session, character)
    farm = await farm_for_house(session, house.id) if house else None
    plot = await session.get(FarmPlot, payload.plot_id)
    if not farm or not plot or plot.farm_id != farm.id or not plot.crop_slug:
        raise HTTPException(404, "Растение на грядке не найдено.")
    if plot.watered_at:
        raise HTTPException(400, "Грядка уже полита.")
    plot.watered_at = datetime.now(timezone.utc)
    character.experience += 2
    apply_levels(character)
    return {"ok": True, "message": "Грядка полита вручную."}


@router.post("/farm/harvest")
async def harvest_plot(
    payload: FarmPlotRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    _, _, _, house = await household_context(session, character)
    farm = await farm_for_house(session, house.id) if house else None
    plot = await session.get(FarmPlot, payload.plot_id)
    if not farm or not plot or plot.farm_id != farm.id or not plot.crop_slug:
        raise HTTPException(404, "Урожай не найден.")
    if not plot.watered_at:
        raise HTTPException(400, "Сначала полейте грядку.")
    ready_at = _aware(plot.ready_at)
    if not ready_at or datetime.now(timezone.utc) < ready_at:
        raise HTTPException(400, "Урожай ещё не созрел.")
    crop_slug = plot.crop_slug
    crop = CROPS[crop_slug]
    accepted = await add_crop_stock(session, farm, crop_slug, int(crop["yield"]))
    if accepted <= 0:
        raise HTTPException(400, "Амбар заполнен. Продайте или используйте часть урожая.")
    clear_plot(plot)
    character.experience += 4
    apply_levels(character)
    return {"ok": True, "message": f"Собрано {accepted} ед.: {crop['name']}."}


@router.post("/farm/assign")
async def assign_farmer(
    payload: FarmAssignRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    _, member_ids, _, house = await household_context(session, character)
    farm = await farm_for_house(session, house.id) if house else None
    if not farm:
        raise HTTPException(404, "Ферма не построена.")
    if payload.npc_id is None:
        farm.farmer_npc_id = None
        return {"ok": True, "message": "Фермер снят с работы. Грядки обслуживаются вручную."}
    npc = await session.get(NpcUnit, payload.npc_id)
    if not npc or npc.character_id not in member_ids or npc.npc_type != "peasant" or not npc.alive:
        raise HTTPException(404, "Подходящий фермер не найден.")
    sync_npc_vitals(npc)
    if npc.hunger >= 90 or npc.fatigue >= 90:
        raise HTTPException(400, "Этот фермер слишком голоден или устал.")
    farm.farmer_npc_id = npc.id
    return {"ok": True, "message": f"{npc.name} назначен на ферму и автоматически обслуживает 2 грядки."}


@router.post("/farm/feed")
async def feed_npc_from_farm(
    payload: FarmFeedRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    _, member_ids, _, house = await household_context(session, character)
    farm = await farm_for_house(session, house.id) if house else None
    npc = await session.get(NpcUnit, payload.npc_id)
    crop = CROPS.get(payload.crop_slug)
    if not farm or not npc or npc.character_id not in member_ids or not npc.alive or not crop:
        raise HTTPException(404, "Не удалось накормить NPC.")
    await take_crop_stock(session, farm, payload.crop_slug, 1)
    sync_npc_vitals(npc)
    restored = int(crop["hunger_restore"])
    npc.hunger = max(0, npc.hunger - restored)
    npc.starvation_started_at = None
    return {"ok": True, "message": f"{npc.name} поел: голод уменьшен на {restored}."}


@router.post("/farm/auto-feed")
async def set_auto_feed(
    payload: FarmAutoFeedRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    _, _, _, house = await household_context(session, character)
    farm = await farm_for_house(session, house.id) if house else None
    if not farm:
        raise HTTPException(404, "Ферма не построена.")
    farm.auto_feed = payload.enabled
    return {"ok": True, "message": "Автокормление включено." if payload.enabled else "Автокормление отключено."}


@router.post("/farm/market/list")
async def list_farm_crop(
    payload: FarmListingRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    _, _, _, house = await household_context(session, character)
    farm = await farm_for_house(session, house.id) if house else None
    crop = CROPS.get(payload.crop_slug)
    if not farm or not crop:
        raise HTTPException(404, "Ферма или культура не найдена.")
    active_count = await session.scalar(select(func.count(FarmMarketListing.id)).where(
        FarmMarketListing.seller_character_id == character.id,
        FarmMarketListing.status == "active",
        FarmMarketListing.expires_at > datetime.now(timezone.utc),
    ))
    if int(active_count or 0) >= 5:
        raise HTTPException(400, "Можно держать не больше пяти объявлений.")
    base = int(crop["base_price"])
    minimum = max(1, (base + 1) // 2)
    maximum = base * 2
    if not minimum <= payload.unit_price <= maximum:
        raise HTTPException(400, f"Цена должна быть от {minimum} до {maximum} монет за единицу.")
    await take_crop_stock(session, farm, payload.crop_slug, payload.quantity)
    listing = FarmMarketListing(
        seller_character_id=character.id, crop_slug=payload.crop_slug,
        quantity=payload.quantity, unit_price=payload.unit_price,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    session.add(listing)
    return {"ok": True, "message": "Урожай выставлен на торговой площади."}


@router.post("/farm/market/buy")
async def buy_farm_listing(
    payload: FarmBuyListingRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    buyer = await require_character(user, session)
    _, _, _, buyer_house = await household_context(session, buyer)
    buyer_farm = await farm_for_house(session, buyer_house.id) if buyer_house else None
    listing = await session.get(FarmMarketListing, payload.listing_id)
    if not buyer_farm or not listing or listing.status != "active":
        raise HTTPException(404, "Объявление недоступно.")
    if listing.expires_at <= datetime.now(timezone.utc):
        listing.status = "return_pending"
        raise HTTPException(400, "Срок объявления истёк. Урожай будет возвращён в амбар.")
    if listing.seller_character_id == buyer.id:
        raise HTTPException(400, "Нельзя купить собственный товар.")
    if await barn_used(session, buyer_farm.id) + listing.quantity > buyer_farm.barn_capacity:
        raise HTTPException(400, "В вашем амбаре недостаточно места.")
    seller = await session.get(Character, listing.seller_character_id)
    if not seller:
        raise HTTPException(404, "Продавец не найден.")
    total = listing.quantity * listing.unit_price
    try:
        await change_gold(session, buyer, -total, f"farm_market_buy:{listing.id}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    seller_income = max(1, int(total * (1 - MARKET_COMMISSION)))
    await change_gold(session, seller, seller_income, f"farm_market_sale:{listing.id}")
    await add_crop_stock(session, buyer_farm, listing.crop_slug, listing.quantity)
    listing.status = "sold"
    return {"ok": True, "message": f"Покупка завершена. Продавец получил {seller_income} монет."}


async def current_event_cycle(session: AsyncSession, character: Character) -> EstateEventCycle:
    cycle = await session.scalar(
        select(EstateEventCycle).where(
            EstateEventCycle.character_id == character.id,
            EstateEventCycle.status == "active",
        ).order_by(EstateEventCycle.id.desc())
    )
    if cycle:
        return cycle
    latest = await session.scalar(
        select(EstateEventCycle).where(EstateEventCycle.character_id == character.id)
        .order_by(EstateEventCycle.id.desc())
    )
    if latest and latest.status == "resolved":
        resolved_at = _aware(latest.resolved_at)
        critical_protection = bool(
            latest.result_kind == "critical" and resolved_at
            and datetime.now(timezone.utc) - resolved_at < timedelta(hours=24)
        )
        if not latest.result_acknowledged or latest.last_choice_date == local_date() or critical_protection:
            return latest
    cycle = EstateEventCycle(character_id=character.id)
    session.add(cycle)
    await session.flush()
    return cycle


async def destroy_random_plots(session: AsyncSession, farm: Farm | None, count: int) -> int:
    if not farm:
        return 0
    result = await session.execute(
        select(FarmPlot).where(FarmPlot.farm_id == farm.id, FarmPlot.crop_slug.is_not(None))
    )
    plots = list(result.scalars())
    selected = sample(plots, min(count, len(plots))) if plots else []
    for plot in selected:
        clear_plot(plot)
    return len(selected)


async def remove_stock_percent(session: AsyncSession, farm: Farm | None, percent: int) -> int:
    if not farm:
        return 0
    rows = await stock_rows(session, farm.id)
    removed = 0
    for row in rows:
        amount = max(0, min(row.quantity, (row.quantity * percent + 99) // 100))
        row.quantity -= amount
        removed += amount
        if row.quantity <= 0:
            await session.delete(row)
    return removed


async def remove_random_inventory(session: AsyncSession, character: Character, count: int) -> list[str]:
    protected = set(NPC_UPGRADE_ITEMS) | {"development_points_30", "house_repair_potion"}
    result = await session.execute(
        select(InventoryItem, ItemTemplate)
        .join(ItemTemplate, ItemTemplate.id == InventoryItem.item_id)
        .where(
            InventoryItem.character_id == character.id,
            InventoryItem.quantity > 0,
            InventoryItem.equipped.is_(False),
        )
    )
    candidates = [(inv, item) for inv, item in result.all() if item.slug not in protected]
    picked = sample(candidates, min(count, len(candidates))) if candidates else []
    removed = []
    for inv, item in picked:
        removed.append(item.name)
        inv.quantity -= 1
        if inv.quantity <= 0:
            await session.delete(inv)
    return removed


async def event_impact(
    session: AsyncSession,
    character: Character,
    event_id: str,
    partial: bool,
    cycle: EstateEventCycle | None = None,
) -> str:
    members, member_ids, _, house = await household_context(session, character)
    farm = await farm_for_house(session, house.id) if house else None
    scale = 0.5 if partial else 1.0
    event = EVENT_BY_ID[event_id]
    title = str(event["title"])

    if event_id == "guard_revolt":
        damage = max(1, int(randint(40, 50) * scale))
        if house:
            house.integrity = max(0, house.integrity - damage)
        guards_result = await session.execute(select(NpcUnit).where(
            NpcUnit.character_id.in_(member_ids), NpcUnit.npc_type == "guard", NpcUnit.alive.is_(True)
        ).order_by(NpcUnit.fatigue.desc(), NpcUnit.hunger.desc()))
        guards = list(guards_result.scalars())
        extra = ""
        if guards:
            guard = guards[0]
            sync_npc_vitals(guard)
            recent_guard_death = await session.scalar(
                select(EstateEventCycle.id).where(
                    EstateEventCycle.character_id == character.id,
                    EstateEventCycle.guard_death_applied.is_(True),
                    EstateEventCycle.resolved_at >= datetime.now(timezone.utc) - timedelta(days=14),
                    *( [EstateEventCycle.id != cycle.id] if cycle and cycle.id else [] ),
                ).limit(1)
            )
            may_die = bool(
                not partial and not recent_guard_death
                and (guard.fatigue >= 90 or guard.hunger >= 90)
            )
            if may_die:
                guard.alive = False
                guard.status = "dead"
                if cycle:
                    cycle.guard_death_applied = True
                extra = f" {guard.name} погиб во время мятежа."
            else:
                guard.status = "resting"
                guard.assignment = "injured"
                guard.available_at = datetime.now(timezone.utc) + timedelta(hours=24)
                extra = f" {guard.name} ранен и отдыхает 24 часа."
        return f"{title}: владение потеряло {damage} прочности.{extra}"

    if event_id in {"captain_plot", "gate_betrayal", "guard_desertion"}:
        guards_result = await session.execute(select(NpcUnit).where(
            NpcUnit.character_id.in_(member_ids), NpcUnit.npc_type == "guard", NpcUnit.alive.is_(True)
        ).order_by(NpcUnit.level.desc()))
        guard = guards_result.scalars().first()
        if guard:
            hours = 12 if partial else (48 if event_id == "guard_desertion" else 24)
            guard.status = "resting"
            guard.assignment = "event_recovery"
            guard.available_at = datetime.now(timezone.utc) + timedelta(hours=hours)
            if event_id == "gate_betrayal" and house:
                damage = max(1, int(randint(18, 28) * scale))
                house.integrity = max(0, house.integrity - damage)
                return f"{title}: {guard.name} выбыл на {hours} ч., дом потерял {damage} прочности."
            return f"{title}: {guard.name} недоступен {hours} часов."
        damage = max(1, int(randint(12, 22) * scale))
        if house:
            house.integrity = max(0, house.integrity - damage)
        return f"{title}: стражи нет, владение потеряло {damage} прочности."

    if event_id == "peasant_theft":
        removed = await remove_stock_percent(session, farm, 25 if partial else 50)
        return f"{title}: из амбара пропало {removed} ед. урожая."
    if event_id == "harvest_riot":
        removed = await destroy_random_plots(session, farm, 1 if partial else 3)
        return f"{title}: уничтожено грядок — {removed}."
    if event_id == "barn_rot":
        removed = await remove_stock_percent(session, farm, 15 if partial else 30)
        return f"{title}: испорчено {removed} ед. запасов."
    if event_id == "seed_swap":
        removed = await destroy_random_plots(session, farm, 1 if partial else 2)
        return f"{title}: опустело грядок — {removed}."

    if event_id == "bandit_raid":
        removed = await remove_random_inventory(session, character, 2 if partial else 5)
        return f"{title}: потеряны предметы: {', '.join(removed) if removed else 'подходящих вещей не было'}."
    if event_id == "trade_ambush":
        percent = randint(10, 15) if partial else randint(20, 30)
        lost = min(character.gold, max(0, int(character.gold * percent / 100)))
        if lost:
            await change_gold(session, character, -lost, "estate_event:trade_ambush")
        return f"{title}: потеряно {lost} монет ({percent}%)."
    if event_id == "warehouse_breakin":
        removed = await remove_random_inventory(session, character, 1 if partial else 3)
        stock_lost = await remove_stock_percent(session, farm, 10 if partial else 20)
        return f"{title}: пропало предметов {len(removed)} и {stock_lost} ед. урожая."
    if event_id == "false_taxmen":
        percent = 10 if partial else 20
        lost = min(character.gold, int(character.gold * percent / 100))
        if lost:
            await change_gold(session, character, -lost, "estate_event:false_tax")
        return f"{title}: отдано {lost} монет."

    if event_id == "monster_horde":
        damage = max(1, int(randint(25, 35) * scale))
        if house:
            house.integrity = max(0, house.integrity - damage)
        return f"{title}: владение потеряло {damage} прочности."
    if event_id == "dragon_over_farm":
        removed = await destroy_random_plots(session, farm, 1 if partial else 2)
        return f"{title}: дракон уничтожил грядок — {removed}."
    if event_id == "rift_rats":
        removed = await remove_stock_percent(session, farm, 20 if partial else 40)
        return f"{title}: крысы съели {removed} ед. еды."
    if event_id == "walking_plague":
        fatigue = 10 if partial else 20
        hunger = 12 if partial else 25
        result = await session.execute(select(NpcUnit).where(
            NpcUnit.character_id.in_(member_ids), NpcUnit.alive.is_(True)
        ))
        count = 0
        for npc in result.scalars():
            sync_npc_vitals(npc)
            npc.fatigue = min(100, npc.fatigue + fatigue)
            npc.hunger = min(100, npc.hunger + hunger)
            count += 1
        return f"{title}: {count} NPC получили +{fatigue} усталости и +{hunger} голода."

    if event_id == "magic_storm":
        damage = max(1, int(20 * scale))
        if house:
            house.integrity = max(0, house.integrity - damage)
        return f"{title}: владение потеряло {damage} прочности."
    if event_id == "great_drought":
        hours = 4 if partial else 8
        if farm:
            result = await session.execute(select(FarmPlot).where(
                FarmPlot.farm_id == farm.id, FarmPlot.crop_slug.is_not(None)
            ))
            for plot in result.scalars():
                if plot.ready_at:
                    plot.ready_at = _aware(plot.ready_at) + timedelta(hours=hours)
        return f"{title}: рост культур задержан на {hours} часов."
    if event_id == "cursed_rain":
        removed = await destroy_random_plots(session, farm, 1 if partial else 2)
        return f"{title}: пострадало грядок — {removed}."
    if event_id == "forest_wrath":
        removed = await remove_stock_percent(session, farm, 12 if partial else 25)
        if removed:
            return f"{title}: духи забрали {removed} ед. урожая."
        lost = min(character.gold, 8 if partial else 15)
        if lost:
            await change_gold(session, character, -lost, "estate_event:forest_wrath")
        return f"{title}: духи забрали {lost} монет."
    return f"{title}: событие произошло, но ущерб оказался минимальным."


async def resolve_event_cycle(
    session: AsyncSession,
    character: Character,
    cycle: EstateEventCycle,
) -> None:
    chosen = json_list(cycle.chosen_event_ids)
    previous = await session.scalar(
        select(EstateEventCycle).where(
            EstateEventCycle.character_id == character.id,
            EstateEventCycle.id != cycle.id,
            EstateEventCycle.status == "resolved",
        ).order_by(EstateEventCycle.id.desc())
    )
    excluded = {str(previous.result_event_id)} if previous and previous.result_event_id in EVENT_BY_ID else set()
    system_ids = event_options(exclude=excluded, count=3)
    cycle.system_event_ids = __import__("json").dumps(system_ids, ensure_ascii=False)
    exact = set(chosen) & set(system_ids)
    cycle.matched_count = len(exact)
    cycle.resolved_at = datetime.now(timezone.utc)
    cycle.status = "resolved"
    if exact:
        reward = {1: 30, 2: 45, 3: 70}.get(len(exact), 30)
        potion_slug = choice(["healing_potion", "house_repair_potion", "mana_crystal"])
        item = await grant_inventory_item(session, character, potion_slug)
        await change_gold(session, character, reward, "estate_event_success")
        cycle.result_kind = "success"
        cycle.reward_gold = reward
        cycle.reward_item_slug = potion_slug
        cycle.result_event_id = next(iter(exact))
        cycle.result_text = f"Событие предотвращено. Получено {reward} монет и предмет «{item.name}»."
        return
    chosen_categories = {str(EVENT_BY_ID[item]["category"]) for item in chosen if item in EVENT_BY_ID}
    category_matches = [item for item in system_ids if str(EVENT_BY_ID[item]["category"]) in chosen_categories]
    partial = bool(category_matches)
    selected = choice(category_matches or system_ids)
    cycle.result_event_id = selected
    cycle.result_kind = "partial" if partial else "critical"
    cycle.result_text = await event_impact(session, character, selected, partial=partial, cycle=cycle)


@router.get("/events")
async def estate_events_center(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    cycle = await current_event_cycle(session, character)
    chosen = json_list(cycle.chosen_event_ids)
    system_ids = json_list(cycle.system_event_ids)
    options_map = json_dict(cycle.daily_options)
    today = local_date()
    options: list[str] = []
    can_choose = cycle.status == "active" and len(chosen) < 3 and cycle.last_choice_date != today
    if can_choose:
        options = options_map.get(today, [])
        if not options:
            options = event_options(exclude=set(chosen), count=3)
            options_map[today] = options
            cycle.daily_options = __import__("json").dumps(options_map, ensure_ascii=False)
    return {
        "cycle_id": cycle.id,
        "status": cycle.status,
        "tutorial_required": not character.events_tutorial_completed,
        "day": min(3, len(chosen) + (1 if can_choose else 0)),
        "chosen": [event_payload(item) for item in chosen if item in EVENT_BY_ID],
        "options": [event_payload(item) for item in options if item in EVENT_BY_ID],
        "can_choose": can_choose,
        "next_choice_text": (
            "После критического события действует защита владения на 24 часа."
            if cycle.status == "resolved" and cycle.result_kind == "critical" and _aware(cycle.resolved_at)
            and datetime.now(timezone.utc) - _aware(cycle.resolved_at) < timedelta(hours=24)
            else "Следующий выбор будет доступен завтра."
        ) if not can_choose else None,
        "system": [event_payload(item) for item in system_ids if item in EVENT_BY_ID],
        "result": ({
            "kind": cycle.result_kind,
            "event": event_payload(cycle.result_event_id) if cycle.result_event_id in EVENT_BY_ID else None,
            "text": cycle.result_text,
            "matched_count": cycle.matched_count,
            "reward_gold": cycle.reward_gold,
            "reward_item_slug": cycle.reward_item_slug,
        } if cycle.status == "resolved" else None),
        "rules": {
            "success": "Хотя бы одно точное совпадение: 30 монет и зелье. За 2–3 совпадения награда выше.",
            "partial": "Совпала категория: ущерб события уменьшается вдвое.",
            "critical": "Нет совпадений: применяется одно критическое последствие.",
        },
    }


@router.post("/events/choose")
async def choose_estate_event(
    payload: EstateEventChooseRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    cycle = await current_event_cycle(session, character)
    if cycle.status != "active":
        raise HTTPException(400, "Этот цикл уже завершён.")
    today = local_date()
    if cycle.last_choice_date == today:
        raise HTTPException(400, "Сегодня карточка уже выбрана.")
    options_map = json_dict(cycle.daily_options)
    options = options_map.get(today, [])
    if payload.event_id not in options or payload.event_id not in EVENT_BY_ID:
        raise HTTPException(400, "Эта карточка сегодня недоступна.")
    chosen = json_list(cycle.chosen_event_ids)
    chosen.append(payload.event_id)
    cycle.chosen_event_ids = __import__("json").dumps(chosen, ensure_ascii=False)
    cycle.last_choice_date = today
    if len(chosen) >= 3:
        await resolve_event_cycle(session, character, cycle)
        return {"ok": True, "resolved": True, "message": "Три предостережения выбраны. Судьба открыла свои карты."}
    return {"ok": True, "resolved": False, "message": f"Карточка сохранена. Выбор {len(chosen)}/3."}


@router.post("/tutorial/{kind}/complete")
async def complete_game_tutorial(
    kind: str,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    if kind == "farm":
        character.farm_tutorial_completed = True
    elif kind == "events":
        character.events_tutorial_completed = True
    else:
        raise HTTPException(404, "Неизвестное обучение.")
    return {"ok": True}


@router.post("/events/result/acknowledge")
async def acknowledge_event_result(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    cycle = await session.scalar(
        select(EstateEventCycle).where(
            EstateEventCycle.character_id == character.id,
            EstateEventCycle.status == "resolved",
            EstateEventCycle.result_acknowledged.is_(False),
        ).order_by(EstateEventCycle.id.desc())
    )
    if cycle:
        cycle.result_acknowledged = True
    return {"ok": True}


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
    repair_potions = await session.scalar(
        select(func.coalesce(func.sum(InventoryItem.quantity), 0))
        .join(ItemTemplate, ItemTemplate.id == InventoryItem.item_id)
        .where(
            InventoryItem.character_id.in_(member_ids),
            ItemTemplate.slug == "house_repair_potion",
        )
    )
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
        "repair_potions": int(repair_potions or 0),
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
        "prices": {"guard": 80, "peasant": FARMER_PRICE},
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
            "fatigue": "Отдых 2 часа снимает 35 усталости, отдых 4 часа — 60. Во время отдыха смерть от переутомления невозможна.",
        },
    }


@router.post("/npcs/buy")
async def buy_npc_unit(
    payload: NpcBuyRequest,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    price = 80 if payload.npc_type == "guard" else FARMER_PRICE
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
    plan = npc_upgrade_plan(npc.level)
    if plan["max_level"]:
        raise HTTPException(400, "NPC уже достиг максимального 50-го уровня.")
    collected = await household_materials(session, member_ids)
    required = npc_upgrade_requirements(npc.npc_type)
    if plan["requires_kit"]:
        missing = [slug for slug in required if slug not in collected]
        if missing:
            raise HTTPException(400, "Для возвышения соберите полный комплект из 5 предметов в Магазине дня.")
    cost = int(plan["cost"])
    if cost:
        try:
            await change_gold(session, character, -cost, f"npc_upgrade:{npc.npc_type}:{npc.id}")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    if plan["requires_kit"]:
        await consume_household_upgrade_materials(session, member_ids, required)
    ascension = bool(plan["requires_kit"])
    gains = npc_stat_gains(npc.npc_type, ascension=ascension)
    for stat, amount in gains.items():
        setattr(npc, stat, getattr(npc, stat) + amount)
    npc.upgrade_count += 1
    npc.level += 1
    npc.model_variant = npc_model_variant(npc.level)
    npc.fatigue = max(0, npc.fatigue - (20 if ascension else 5))
    remaining_materials = await household_materials(session, member_ids)
    owner_name = next((member.name for member in members if member.id == npc.character_id), None)
    cost_text = f" за {cost} монет" if cost else ""
    material_text = " Комплект предметов использован, облик изменён." if ascension else ""
    return {
        "ok": True,
        "message": f"{npc.name} улучшен до уровня {npc.level}{cost_text}.{material_text}",
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
            recovery = 60 if npc.assignment == "rest_long" else 35
            npc.fatigue = max(0, npc.fatigue - recovery)
            npc.exhaustion_started_at = None
        elif npc.status == "training":
            npc.experience += 20
            npc.skill += 2
            npc.endurance += 1
        npc.status = "idle"
        npc.assignment = None
        npc.available_at = None

    sync_npc_vitals(npc, now)
    action = payload.action
    if action in {"rest", "rest_short", "rest_long"}:
        long_rest = action == "rest_long"
        npc.status = "resting"
        npc.assignment = "rest_long" if long_rest else "rest_short"
        npc.available_at = now + timedelta(hours=4 if long_rest else 2)
        npc.last_rest_at = now
        npc.exhaustion_started_at = None
        return {
            "ok": True,
            "message": "Глубокий отдых: через 4 часа усталость уменьшится на 60." if long_rest
                else "Короткий отдых: через 2 часа усталость уменьшится на 35. NPC защищён от смерти во время отдыха.",
        }

    if npc.npc_type == "guard":
        raise HTTPException(400, "Стражнику сейчас доступны отдых, кормление и защита владения.")

    if npc.fatigue >= 90 or npc.hunger >= 90:
        raise HTTPException(400, "Фермер слишком устал или голоден. Сначала дайте ему отдых и еду.")

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
    npc.hunger = min(100, npc.hunger + (10 if action == "field" else 6))
    sync_npc_vitals(npc, now)
    npc.status = "working"
    npc.assignment = action
    npc.available_at = now + timedelta(minutes=minutes)
    npc.experience += 6 + npc.level

    if action == "field":
        reward = randint(4, 8) + npc.level + npc.skill * 2 + npc.endurance // 2
        await change_gold(session, character, reward, "farmer_field")
        message = f"{label}: получено {reward} золота в общий бюджет."
    elif action == "clean":
        if house:
            house.cleanliness = 100
            house.last_cleaning_date = local_date()
        message = "Совместное владение убрано."
    elif action == "garden":
        if house:
            house.repair_energy += 3 + npc.level + npc.skill + npc.endurance // 2
        message = "Сад полит, получена энергия ремонта."
    else:
        character.experience += 4 + npc.skill // 2
        apply_levels(character)
        message = "Туалеты очищены. Получен опыт."

    if npc.fatigue >= 100 or npc.hunger >= 100:
        message += " NPC истощён и больше не сможет работать, пока не отдохнёт и не поест."
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


@router.post("/estate/repair-potion")
async def repair_estate_with_potion(
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    character = await require_character(user, session)
    _, member_ids, _, house = await household_context(session, character)
    if not house:
        raise HTTPException(404, "Владение не найдено.")
    if house.integrity >= 100:
        raise HTTPException(400, "Владение уже полностью восстановлено.")
    result = await session.execute(
        select(InventoryItem)
        .join(ItemTemplate, ItemTemplate.id == InventoryItem.item_id)
        .where(
            InventoryItem.character_id.in_(member_ids),
            ItemTemplate.slug == "house_repair_potion",
            InventoryItem.quantity > 0,
        )
        .order_by(InventoryItem.id)
    )
    potion = result.scalars().first()
    if not potion:
        raise HTTPException(400, "Зелья ремонта дома нет в общем инвентаре.")
    if potion.quantity <= 1:
        await session.delete(potion)
    else:
        potion.quantity -= 1
    restored = 100 - house.integrity
    house.integrity = 100
    return {"ok": True, "restored": restored, "integrity": 100, "message": "Зелье полностью восстановило владение без монет."}


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
    stories_result = await session.execute(select(PlayerStory).where(PlayerStory.is_published.is_(True)))
    stories_by_character = {story.character_id: story for story in stories_result.scalars()}
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
            "story_available": character.id in stories_by_character,
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


@router.get("/friends/{character_id}/story")
async def friend_story(character_id: int, user=Depends(current_miniapp_user), session: AsyncSession=Depends(get_session)):
    await require_character(user, session)
    character = await session.get(Character, character_id)
    story = await session.scalar(
        select(PlayerStory).where(
            PlayerStory.character_id == character_id,
            PlayerStory.is_published.is_(True),
        )
    )
    if not character or not story:
        raise HTTPException(404, "История игрока ещё не опубликована.")
    parts = [
        ("introduction", "Введение", story.introduction, story.introduction_image_file_id),
        ("main_part_one", "Основная часть 1", story.main_part_one, story.main_part_one_image_file_id),
        ("main_part_two", "Основная часть 2", story.main_part_two, story.main_part_two_image_file_id),
        ("ending", "Конец", story.ending, story.ending_image_file_id),
    ]
    return {
        "character": {"id": character.id, "name": character.name, "title": character.title, "level": character.level},
        "parts": [{
            "key": key, "label": label, "text": text,
            "image_available": bool(image_file_id),
            "image_url": f"/api/miniapp/friends/{character.id}/story/{key}/image" if image_file_id else None,
        } for key, label, text, image_file_id in parts],
    }


@router.post("/friends/{character_id}/story/complete")
async def complete_friend_story(
    character_id: int,
    user=Depends(current_miniapp_user),
    session: AsyncSession=Depends(get_session),
):
    reader = await require_character(user, session)
    if character_id == reader.id:
        return {
            "ok": True,
            "counted": False,
            "achievement_unlocked": False,
            "reward": 0,
            "message": "Собственная история не учитывается для секретной ачивки.",
        }

    story = await session.scalar(
        select(PlayerStory).where(
            PlayerStory.character_id == character_id,
            PlayerStory.is_published.is_(True),
        )
    )
    if not story:
        raise HTTPException(404, "История игрока ещё не опубликована.")

    existing = await session.scalar(
        select(StoryRead).where(
            StoryRead.reader_character_id == reader.id,
            StoryRead.story_character_id == character_id,
        )
    )
    counted = existing is None
    if counted:
        session.add(StoryRead(
            reader_character_id=reader.id,
            story_character_id=character_id,
        ))
        await session.flush()

    completed_count = int(await session.scalar(
        select(func.count(StoryRead.id)).where(StoryRead.reader_character_id == reader.id)
    ) or 0)

    achievement_unlocked = False
    reward = 0
    if completed_count >= 6 and not reader.story_reader_achievement_claimed:
        reader.story_reader_achievement_claimed = True
        reward = 20
        await change_gold(session, reader, reward, "achievement:secret_story_reader")
        achievement_unlocked = True

    return {
        "ok": True,
        "counted": counted,
        "achievement_unlocked": achievement_unlocked,
        "reward": reward,
        "gold": reader.gold,
    }


@router.get("/friends/{character_id}/story/{part}/image")
async def friend_story_image(character_id: int, part: str, user=Depends(current_miniapp_user), session: AsyncSession=Depends(get_session)):
    await require_character(user, session)
    story = await session.scalar(
        select(PlayerStory).where(PlayerStory.character_id == character_id, PlayerStory.is_published.is_(True))
    )
    if not story:
        raise HTTPException(404, "История не найдена.")
    fields = {
        "introduction": story.introduction_image_file_id,
        "main_part_one": story.main_part_one_image_file_id,
        "main_part_two": story.main_part_two_image_file_id,
        "ending": story.ending_image_file_id,
    }
    file_id = fields.get(part)
    if not file_id:
        raise HTTPException(404, "Изображение этой части не загружено.")
    return await telegram_file_response(file_id)


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

