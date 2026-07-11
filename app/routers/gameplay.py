from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards import stats_keyboard, professions_keyboard, factions_keyboard
from app.models import User
from app.services import apply_levels, get_character, get_system_media, local_date

router = Router()


async def training_menu(message: Message, session: AsyncSession, telegram_id: int) -> None:
    c = await get_character(session, telegram_id)
    if not c:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    if c.work_ends_at and not c.work_reward_claimed:
        from datetime import datetime, timezone
        if datetime.now(timezone.utc) < c.work_ends_at:
            await message.answer("Во время работы тренироваться нельзя.")
            return
    if c.training_date == local_date():
        await message.answer("Сегодня вы уже тренировались.")
        return
    await message.answer("Выберите характеристику:", reply_markup=stats_keyboard())


@router.message(Command("тренировка", "training"))
async def training(message: Message, session: AsyncSession) -> None:
    await training_menu(message, session, message.from_user.id)


@router.callback_query(F.data == "menu:training")
async def training_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await training_menu(callback.message, session, callback.from_user.id)


@router.callback_query(F.data.startswith("train:"))
async def train_stat(callback: CallbackQuery, session: AsyncSession) -> None:
    c = await get_character(session, callback.from_user.id)
    if not c:
        await callback.answer("Сначала /start", show_alert=True)
        return
    if c.training_date == local_date():
        await callback.answer("Сегодня тренировка уже использована.", show_alert=True)
        return
    stat = callback.data.split(":", 1)[1]
    allowed = {
        "strength": "Сила", "intelligence": "Интеллект", "agility": "Ловкость",
        "magic": "Магия", "luck": "Удача", "endurance": "Выносливость",
    }
    if stat not in allowed:
        await callback.answer("Ошибка характеристики.", show_alert=True)
        return
    setattr(c, stat, getattr(c, stat) + 1)
    c.experience += 10
    c.training_date = local_date()
    levels = apply_levels(c)
    await callback.message.edit_text(
        f"✅ {allowed[stat]} повышена на 1. Получено 10 XP."
        + (f" Новый уровень: {c.level}!" if levels else "")
    )
    await callback.answer()


@router.message(Command("профессии", "professions"))
async def professions(message: Message, session: AsyncSession) -> None:
    c = await get_character(session, message.from_user.id)
    if not c:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    await message.answer(f"Текущая профессия: {c.profession}\nВыберите новую:", reply_markup=professions_keyboard())


@router.callback_query(F.data.startswith("profession:"))
async def select_profession(callback: CallbackQuery, session: AsyncSession) -> None:
    c = await get_character(session, callback.from_user.id)
    profession = callback.data.split(":", 1)[1]
    c.profession = profession
    await callback.message.edit_text(f"✅ Вы выбрали профессию: {profession}")
    await callback.answer()


@router.message(Command("фракции", "factions"))
async def factions(message: Message, session: AsyncSession) -> None:
    c = await get_character(session, message.from_user.id)
    if not c:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    text = (
        "🚩 <b>Фракции Королевства</b>\n\n"
        f"Ваша фракция: {c.faction}\n\n"
        "Западная сторона — порядок, сила и контроль территорий.\n"
        "Нейтральный Диалог — дипломатия, баланс и переговоры."
    )
    file_id = await get_system_media(session, "factions")
    if file_id:
        await message.answer_photo(file_id, caption=text, reply_markup=factions_keyboard())
    else:
        await message.answer(text, reply_markup=factions_keyboard())


@router.callback_query(F.data == "menu:factions")
async def factions_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    c = await get_character(session, callback.from_user.id)
    text = (
        "🚩 <b>Фракции Королевства</b>\n\n"
        f"Ваша фракция: {c.faction}\n\n"
        "Западная сторона — порядок, сила и контроль территорий.\n"
        "Нейтральный Диалог — дипломатия, баланс и переговоры."
    )
    file_id = await get_system_media(session, "factions")
    if file_id:
        await callback.message.answer_photo(file_id, caption=text, reply_markup=factions_keyboard())
    else:
        await callback.message.answer(text, reply_markup=factions_keyboard())


@router.callback_query(F.data.startswith("faction:"))
async def select_faction(callback: CallbackQuery, session: AsyncSession) -> None:
    c = await get_character(session, callback.from_user.id)
    faction = callback.data.split(":", 1)[1]
    c.faction = faction
    await callback.message.edit_text(f"✅ Новая фракция: {faction}")
    await callback.answer()
