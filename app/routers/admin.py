from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.keyboards import (
    admin_attack_players_keyboard, admin_extended_keyboard,
    admin_players_keyboard, admin_roles_keyboard, house_attack_keyboard,
)
from app.models import Character, GameEvent, House, HouseAttack, User
from app.services import apply_levels, change_gold, get_character
router = Router()
ROLES={"citizen":("Гражданин",None),"leader_west":("Лидер фракции «Западная сторона»","Западная сторона"),"leader_neutral":("Лидер фракции «Нейтральный Диалог»","Нейтральный Диалог"),"king":("Король",None),"queen":("Королева",None)}
def is_admin(uid:int)->bool: return uid in get_settings().admins
@router.message(Command("admin"))
async def admin(message:Message):
    if not is_admin(message.from_user.id): return await message.answer("Недостаточно прав.")
    await message.answer("⚙ <b>Админ-панель</b>", reply_markup=admin_main_keyboard())
@router.callback_query(F.data=="admin:home")
async def home(c:CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("Нет прав",show_alert=True)
    await c.answer(); await c.message.edit_text("⚙ <b>Админ-панель</b>",reply_markup=admin_main_keyboard())
@router.callback_query(F.data=="admin:players")
async def players(c:CallbackQuery,session:AsyncSession):
    if not is_admin(c.from_user.id): return await c.answer("Нет прав",show_alert=True)
    result=await session.execute(select(User.telegram_id,Character.name,Character.title).join(Character,Character.user_id==User.id).order_by(Character.name))
    rows=list(result.all()); await c.answer()
    await c.message.edit_text("👥 <b>Выберите игрока</b>",reply_markup=admin_players_keyboard(rows))
@router.callback_query(F.data.startswith("adminplayer:"))
async def player(c:CallbackQuery,session:AsyncSession):
    if not is_admin(c.from_user.id): return await c.answer("Нет прав",show_alert=True)
    tid=int(c.data.split(":")[1]); ch=await get_character(session,tid)
    if not ch: return await c.answer("Игрок не найден",show_alert=True)
    await c.answer(); await c.message.edit_text(f"👤 <b>{ch.name}</b>\nРоль: {ch.title}\nФракция: {ch.faction}",reply_markup=admin_roles_keyboard(tid))
@router.callback_query(F.data.startswith("setrole:"))
async def setrole(c:CallbackQuery,session:AsyncSession):
    if not is_admin(c.from_user.id): return await c.answer("Нет прав",show_alert=True)
    _,tid,key=c.data.split(":",2); ch=await get_character(session,int(tid)); title,faction=ROLES[key]
    ch.title=title
    if key=="citizen": ch.faction="Нет"
    elif faction: ch.faction=faction
    await c.answer("Роль назначена",show_alert=True)
    await c.message.edit_text(f"✅ {ch.name}: <b>{title}</b>\nФракция: {ch.faction}",reply_markup=admin_roles_keyboard(int(tid)))
async def find_character(session,tid):
    r=await session.execute(select(Character).join(User).where(User.telegram_id==tid)); return r.scalar_one_or_none()
@router.message(Command("дать_золото"))
async def give_gold(message:Message,session:AsyncSession):
    if not is_admin(message.from_user.id): return
    try: _,tid,amount=message.text.split(); ch=await find_character(session,int(tid)); await change_gold(session,ch,int(amount),f"admin:{message.from_user.id}"); await message.answer(f"Баланс: {ch.gold}")
    except Exception as e: await message.answer(f"Формат: /дать_золото ID СУММА\n{e}")
@router.message(Command("дать_опыт"))
async def give_xp(message:Message,session:AsyncSession):
    if not is_admin(message.from_user.id): return
    try: _,tid,amount=message.text.split(); ch=await find_character(session,int(tid)); ch.experience+=max(0,int(amount)); apply_levels(ch); await message.answer(f"Уровень: {ch.level}")
    except Exception as e: await message.answer(f"Формат: /дать_опыт ID ОПЫТ\n{e}")
@router.message(Command("запустить_событие"))
async def event(message:Message,session:AsyncSession):
    if not is_admin(message.from_user.id): return
    title=message.text.partition(" ")[2].strip()
    if not title: return await message.answer("Формат: /запустить_событие ТЕКСТ")
    session.add(GameEvent(title=title)); await message.answer(f"⚠ Событие: {title}")



@router.callback_query(F.data == "admin:attack_players")
async def admin_attack_players(callback: CallbackQuery, session: AsyncSession) -> None:
    if await deny_callback(callback):
        return
    result = await session.execute(
        select(User.telegram_id, Character.name)
        .join(Character, Character.user_id == User.id)
        .order_by(Character.name)
    )
    players = list(result.all())
    await callback.answer()
    await callback.message.edit_text(
        "🐉 <b>Выберите дом для тестового нападения</b>",
        reply_markup=admin_attack_players_keyboard(players),
    )


@router.callback_query(F.data.startswith("adminattack:"))
async def admin_force_attack(callback: CallbackQuery, session: AsyncSession) -> None:
    if await deny_callback(callback):
        return
    telegram_id = int(callback.data.split(":", 1)[1])
    char = await get_character(session, telegram_id)
    if not char or not char.house:
        await callback.answer("Дом игрока не найден.", show_alert=True)
        return
    existing = await session.execute(
        select(HouseAttack).where(
            HouseAttack.house_id == char.house.id,
            HouseAttack.status.in_(["waiting", "player_fighting", "guards_fighting"]),
        )
    )
    if existing.scalars().first():
        await callback.answer("На этот дом уже идёт нападение.", show_alert=True)
        return
    from datetime import datetime, timedelta, timezone
    from random import choice, randint
    enemies = [
        ("🐉 Дракон", "dragon", 44),
        ("👹 Болотный урод", "monster", 32),
        ("🌀 Аномалия", "anomaly", 40),
    ]
    name, enemy_type, base = choice(enemies)
    attack = HouseAttack(
        house_id=char.house.id,
        enemy_name=name,
        enemy_type=enemy_type,
        enemy_power=base + char.level * 2,
        enemy_hp=60 + base + char.level * 2,
        response_deadline=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    session.add(attack)
    await session.flush()
    try:
        await callback.bot.send_message(
            telegram_id,
            f"⚠ <b>ТЕСТОВОЕ НАПАДЕНИЕ!</b>\n{name} атакует ваш дом.",
            reply_markup=house_attack_keyboard(attack.id),
        )
    except Exception:
        pass
    await callback.answer("Нападение создано.", show_alert=True)


@router.callback_query(F.data == "admin:repair_all")
async def admin_repair_all(callback: CallbackQuery, session: AsyncSession) -> None:
    if await deny_callback(callback):
        return
    result = await session.execute(select(House))
    houses = list(result.scalars())
    for house in houses:
        house.integrity = 100
    await callback.answer(f"Восстановлено домов: {len(houses)}", show_alert=True)


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    if await deny_callback(callback):
        return
    from sqlalchemy import func
    players = await session.scalar(select(func.count(Character.id))) or 0
    houses = await session.scalar(select(func.count(House.id))) or 0
    active = await session.scalar(
        select(func.count(HouseAttack.id)).where(
            HouseAttack.status.in_(["waiting", "player_fighting", "guards_fighting"])
        )
    ) or 0
    await callback.answer()
    await callback.message.edit_text(
        f"📊 <b>Статистика Королевства</b>\n\n"
        f"Игроков: {players}\n"
        f"Домов: {houses}\n"
        f"Активных нападений: {active}",
        reply_markup=admin_extended_keyboard(),
    )
