from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.keyboards import house_panel_keyboard, main_menu
from app.services import get_character, xp_for_next
from app.states import ChangeHousePhoto, ChangePortrait

router = Router()


async def send_section_card(target: Message, session: AsyncSession, key: str, caption: str, reply_markup=None) -> None:
    file_id = await get_system_media(session, key)
    if file_id:
        await target.answer_photo(file_id, caption=caption, reply_markup=reply_markup)
    else:
        await target.answer(caption, reply_markup=reply_markup)


async def send_profile(target: Message, session: AsyncSession, telegram_id: int) -> None:
    c = await get_character(session, telegram_id)
    if not c:
        await target.answer("Сначала зарегистрируйтесь: /start")
        return
    text = (
        f"👑 <b>{c.name}</b>\n"
        f"⭐ Уровень: {c.level}\n"
        f"✨ Опыт: {c.experience}/{xp_for_next(c.level)}\n"
        f"❤️ Здоровье: {c.health}\n"
        f"🔮 Мана: {c.mana}\n"
        f"💪 Сила: {c.strength}\n"
        f"🧠 Интеллект: {c.intelligence}\n"
        f"🏃 Ловкость: {c.agility}\n"
        f"🪄 Магия: {c.magic}\n"
        f"🍀 Удача: {c.luck}\n"
        f"🛡 Выносливость: {c.endurance}\n"
        f"🎭 Харизма: {c.charisma}\n"
        f"🪙 Золото: {c.gold}\n"
        f"🧰 Профессия: {c.profession}\n"
        f"🏷 Титул: {c.title}\n"
        f"📣 Репутация: {c.reputation}\n"
        f"🚩 Фракция: {c.faction}\n"
        f"👥 Статус: {c.social_status}"
    )
    await target.answer_photo(c.portrait_file_id, caption=text)


@router.message(Command("профиль", "персонаж", "profile", "character"))
async def profile(message: Message, session: AsyncSession) -> None:
    await send_profile(message, session, message.from_user.id)


@router.callback_query(F.data == "menu:profile")
async def profile_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await send_profile(callback.message, session, callback.from_user.id)


@router.message(Command("дом", "house"))
async def house(message: Message, session: AsyncSession) -> None:
    c = await get_character(session, message.from_user.id)
    if not c or not c.house:
        await message.answer("Дом не найден. Используйте /start.")
        return
    h = c.house
    text = (
        f"🏰 <b>{h.name}</b>\n"
        f"👤 Владелец: {c.name}\n"
        f"📍 Расположение: {h.location}\n"
        f"📖 {h.description}\n"
        f"⭐ Уровень: {h.level}\n"
        f"💰 Стоимость: {h.value}\n"
        f"🛡 Защита: {h.defense}\n"
        f"📜 Статус: {h.status}\n"
        f"🏗 Прочность: {h.integrity}/100\n"
        f"✨ Энергия ремонта: {h.repair_energy}"
    )
    await message.answer_photo(h.image_file_id, caption=text)


@router.callback_query(F.data == "menu:house")
async def house_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    c = await get_character(session, callback.from_user.id)
    if not c or not c.house:
        await callback.message.answer("Дом не найден. Сначала /start в личном чате.")
        return
    h = c.house
    text = (f"🏰 <b>{h.name}</b>\n👤 Владелец: {c.name}\n📍 Расположение: {h.location}\n"
            f"📖 {h.description}\n⭐ Уровень: {h.level}\n💰 Стоимость: {h.value}\n"
            f"🛡 Защита: {h.defense}\n📜 Статус: {h.status}")
    await callback.message.answer_photo(h.image_file_id, caption=text)


@router.message(Command("сменить_портрет"))
async def change_portrait(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not await get_character(session, message.from_user.id):
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    await state.set_state(ChangePortrait.photo)
    await message.answer("Пришлите новую фотографию персонажа. Она заменит предыдущую.")


@router.message(ChangePortrait.photo, F.photo)
async def save_portrait(message: Message, state: FSMContext, session: AsyncSession) -> None:
    c = await get_character(session, message.from_user.id)
    c.portrait_file_id = message.photo[-1].file_id
    await state.clear()
    await message.answer("✅ Портрет персонажа обновлён.")


@router.message(Command("сменить_фото_дома"))
async def change_house(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not await get_character(session, message.from_user.id):
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    await state.set_state(ChangeHousePhoto.photo)
    await message.answer("Пришлите новую фотографию дома. Она заменит предыдущую.")


@router.message(ChangeHousePhoto.photo, F.photo)
async def save_house(message: Message, state: FSMContext, session: AsyncSession) -> None:
    c = await get_character(session, message.from_user.id)
    c.house.image_file_id = message.photo[-1].file_id
    await state.clear()
    await message.answer("✅ Фотография дома обновлена.")


@router.message(Command("меню", "menu"))
async def menu(message: Message) -> None:
    await message.answer(
        "👑 <b>Центральная панель Королевства</b>\nВыберите раздел:",
        reply_markup=main_menu(message.from_user.id in get_settings().admins),
    )


@router.callback_query(F.data == "menu:development")
async def development_card(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    c = await get_character(session, callback.from_user.id)
    if not c:
        await callback.message.answer("Сначала зарегистрируйтесь: /start")
        return
    from app.keyboards import stats_keyboard
    caption = (
        "🏋 <b>Зал развития</b>\n\n"
        f"Герой: {c.name}\nУровень: {c.level}\n"
        f"Опыт: {c.experience}/{xp_for_next(c.level)}\n\n"
        "Выберите характеристику для ежедневной тренировки."
    )
    await send_section_card(callback.message, session, "development", caption, stats_keyboard())


@router.callback_query(F.data == "menu:treasury")
async def treasury_card(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    c = await get_character(session, callback.from_user.id)
    if not c:
        await callback.message.answer("Сначала зарегистрируйтесь: /start")
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💼 Начать работу", callback_data="menu:work")],
        [InlineKeyboardButton(text="📦 Получить награду", callback_data="treasury:claim")],
    ])
    caption = (
        "💰 <b>Королевская казна</b>\n\n"
        f"Ваше золото: {c.gold} 🪙\nРабот сегодня: {c.work_count}/2\n\n"
        "Здесь можно начать работу или забрать готовую награду."
    )
    await send_section_card(callback.message, session, "treasury", caption, keyboard)
