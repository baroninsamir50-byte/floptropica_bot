from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.keyboards import admin_main_keyboard, admin_players_keyboard, admin_roles_keyboard
from app.models import Character, GameEvent, User
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
