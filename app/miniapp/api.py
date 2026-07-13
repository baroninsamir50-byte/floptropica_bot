from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from aiogram import Bot
from aiogram.types import BufferedInputFile
from io import BytesIO
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionFactory
from app.models import InventoryItem, ItemTemplate, OwnedNpc, Duel, Character, User, SystemMedia
from app.miniapp.auth import TelegramMiniAppUser, current_miniapp_user
from app.services import (
    buy_item, claim_work, get_character, get_daily_shop_items,
    get_equipment_bonuses, get_system_media, local_date,
    start_work, toggle_equip, xp_for_next, claim_daily_reward,
    level_income_multiplier, level_rank, set_system_media, change_gold, apply_levels,
)
from app.work_catalog import available_professions, profession_by_key, title_can_use
from app.miniapp.duel_engine import STYLES, initialize_duel, perform_action, log_list

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
    media_keys=("home_bg","hero_bg","house_bg","treasury","shop","development","factions","map","games_bg","inventory_bg","loading_bg","app_logo","topbar_bg","nav_bg","card_texture","frame_hero","frame_house","icon_hero","icon_house","icon_treasury","icon_shop","icon_map","icon_games","icon_factions","icon_inventory","icon_development","icon_daily","duel_bg","duel_frame","duel_vs","icon_customization")
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
    "icon_games","icon_factions","icon_inventory","icon_development","icon_daily",
    "duel_bg","duel_frame","duel_vs","icon_customization",
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
