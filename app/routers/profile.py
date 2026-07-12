from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.keyboards import development_keyboard, house_panel_keyboard, main_menu, treasury_keyboard
from app.services import (
    get_character, get_equipment_bonuses, get_system_media, xp_for_next,
    level_income_multiplier, level_rank,
)
from app.states import ChangeHousePhoto, ChangePortrait
router = Router()

async def section(target, session, key, caption, keyboard=None):
    file_id = await get_system_media(session, key)
    if file_id: await target.answer_photo(file_id, caption=caption, reply_markup=keyboard)
    else: await target.answer(caption, reply_markup=keyboard)

async def hero_caption(session, c):
    bonuses = await get_equipment_bonuses(session, c.id)
    total=lambda k: getattr(c,k)+bonuses.get(k,0)
    return (
        f"👑 <b>{c.name}</b>\n⭐ Уровень: {c.level}\n✨ Опыт: {c.experience}/{xp_for_next(c.level)}\n"
        f"🎯 Свободные очки развития: {c.development_points}\n"
        f"🏅 Ранг: {level_rank(c.level)}\n"
        f"💹 Бонус дохода: +{int((level_income_multiplier(c.level)-1)*100)}%\n\n"
        f"❤️ Здоровье: {total('health')}\n🔮 Мана: {total('mana')}\n💪 Сила: {total('strength')}\n"
        f"🧠 Интеллект: {total('intelligence')}\n🏃 Ловкость: {total('agility')}\n"
        f"🪄 Магия: {total('magic')}\n🍀 Удача: {total('luck')}\n"
        f"🛡 Выносливость: {total('endurance')}\n🎭 Харизма: {total('charisma')}\n\n"
        f"🪙 Золото: {c.gold}\n🧰 Профессия: {c.profession}\n🏷 Роль: {c.title}\n"
        f"📣 Репутация: {c.reputation}\n🚩 Фракция: {c.faction}\n👥 Статус: {c.social_status}"
    )

async def send_profile(target, session, tid):
    c=await get_character(session,tid)
    if not c: return await target.answer("Сначала зарегистрируйтесь: /start")
    await target.answer_photo(c.portrait_file_id,caption=await hero_caption(session,c))

@router.message(Command("profile","character","профиль","персонаж"))
async def profile(message:Message,session:AsyncSession): await send_profile(message,session,message.from_user.id)
@router.callback_query(F.data=="menu:profile")
async def profile_cb(callback:CallbackQuery,session:AsyncSession):
    await callback.answer(); await send_profile(callback.message,session,callback.from_user.id)

async def send_house(target,session,tid):
    c=await get_character(session,tid)
    if not c or not c.house: return await target.answer("Дом не найден. Используйте /start.")
    h=c.house
    caption=(f"🏰 <b>{h.name}</b>\n👤 Владелец: {c.name}\n📍 {h.location}\n📖 {h.description}\n"
             f"⭐ Уровень: {h.level}\n💰 Стоимость: {h.value}\n🛡 Защита: {h.defense}\n"
             f"🏗 Прочность: {h.integrity}/100\n✨ Энергия ремонта: {h.repair_energy}")
    await target.answer_photo(h.image_file_id,caption=caption,reply_markup=house_panel_keyboard())
@router.message(Command("house","дом"))
async def house(message:Message,session:AsyncSession): await send_house(message,session,message.from_user.id)
@router.callback_query(F.data=="menu:house")
async def house_cb(callback:CallbackQuery,session:AsyncSession):
    await callback.answer(); await send_house(callback.message,session,callback.from_user.id)

@router.message(Command("change_portrait","сменить_портрет"))
async def change_portrait(message:Message,state:FSMContext,session:AsyncSession):
    if message.chat.type!="private": return await message.answer("Портрет меняется только в личном чате.")
    if not await get_character(session,message.from_user.id): return await message.answer("Сначала /start")
    await state.set_state(ChangePortrait.photo); await message.answer("Пришлите новую фотографию персонажа.")
@router.message(ChangePortrait.photo,F.photo)
async def save_portrait(message:Message,state:FSMContext,session:AsyncSession):
    c=await get_character(session,message.from_user.id); c.portrait_file_id=message.photo[-1].file_id
    await state.clear(); await message.answer("✅ Портрет обновлён.")

@router.message(Command("change_house_photo","сменить_фото_дома"))
async def change_house(message:Message,state:FSMContext,session:AsyncSession):
    if message.chat.type!="private": return await message.answer("Фото дома меняется только в личном чате.")
    if not await get_character(session,message.from_user.id): return await message.answer("Сначала /start")
    await state.set_state(ChangeHousePhoto.photo); await message.answer("Пришлите новую фотографию дома.")
@router.message(ChangeHousePhoto.photo,F.photo)
async def save_house(message:Message,state:FSMContext,session:AsyncSession):
    c=await get_character(session,message.from_user.id); c.house.image_file_id=message.photo[-1].file_id
    await state.clear(); await message.answer("✅ Фото дома обновлено.")

@router.message(Command("menu","меню"))
async def menu(message:Message):
    await message.answer("👑 <b>Центральная панель Королевства</b>",reply_markup=main_menu(message.from_user.id in get_settings().admins))

@router.callback_query(F.data=="menu:development")
async def development(callback:CallbackQuery,session:AsyncSession):
    await callback.answer(); c=await get_character(session,callback.from_user.id)
    if not c: return await callback.message.answer("Сначала /start")
    await section(callback.message,session,"development",
        f"🏋 <b>Развитие</b>\n\nОсталось очков: <b>{c.development_points}</b> из 100\n"
        "Очки выдаются один раз и навсегда повышают выбранные показатели.",development_keyboard())

@router.callback_query(F.data.startswith("dev:"))
async def allocate(callback:CallbackQuery,session:AsyncSession):
    c=await get_character(session,callback.from_user.id)
    if not c: return await callback.answer("Сначала /start",show_alert=True)
    _,stat,raw=callback.data.split(":",2); amount=int(raw)
    names={"strength":"Сила","intelligence":"Интеллект","agility":"Ловкость","magic":"Магия",
           "luck":"Удача","endurance":"Выносливость","charisma":"Харизма","health":"Здоровье","mana":"Мана"}
    if stat not in names: return await callback.answer("Ошибка.",show_alert=True)
    if c.development_points<amount: return await callback.answer("Недостаточно очков.",show_alert=True)
    c.development_points-=amount; setattr(c,stat,getattr(c,stat)+amount)
    await callback.answer(f"{names[stat]} +{amount}. Осталось {c.development_points}.",show_alert=True)

@router.callback_query(F.data=="menu:treasury")
async def treasury(callback:CallbackQuery,session:AsyncSession):
    await callback.answer(); c=await get_character(session,callback.from_user.id)
    if not c: return await callback.message.answer("Сначала /start")
    await section(callback.message,session,"treasury",
        f"💰 <b>Казна и работа</b>\n\nЗолото: {c.gold} 🪙\nПрофессия: {c.profession}\n"
        f"Смен сегодня: {c.work_count}/2\n\nВыберите профессию и начните двухчасовую смену.",treasury_keyboard())

@router.callback_query(F.data=="menu:map")
async def map_cb(callback:CallbackQuery,session:AsyncSession):
    await callback.answer(); file_id=await get_system_media(session,"map")
    caption="🗺 <b>Карта Королевства Флоптропика</b>"
    if file_id: await callback.message.answer_photo(file_id,caption=caption)
    else: await callback.message.answer(caption+"\nКарта ещё не загружена создателем.")
@router.message(Command("map","карта"))
async def map_cmd(message:Message,session:AsyncSession):
    file_id=await get_system_media(session,"map"); caption="🗺 <b>Карта Королевства Флоптропика</b>"
    if file_id: await message.answer_photo(file_id,caption=caption)
    else: await message.answer(caption+"\nКарта ещё не загружена создателем.")
