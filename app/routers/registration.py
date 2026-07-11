from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.keyboards import main_menu
from app.models import Character, House, User
from app.states import Registration

router = Router()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.chat.type != "private":
        me = await message.bot.get_me()
        await message.answer(f"Регистрация проходит в личном чате: https://t.me/{me.username}?start=register")
        return
    exists = await session.scalar(select(User.id).where(User.telegram_id == message.from_user.id))
    if exists:
        await message.answer("С возвращением в Королевство Флоптропика!", reply_markup=main_menu())
        return
    await state.clear()
    await state.set_state(Registration.name)
    await message.answer(
        "👑 Добро пожаловать в Королевство Флоптропика!\n\n"
        "Введите имя вашего персонажа (до 80 символов)."
    )


@router.message(Registration.name)
async def registration_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not 2 <= len(name) <= 80:
        await message.answer("Имя должно содержать от 2 до 80 символов.")
        return
    await state.update_data(name=name)
    await state.set_state(Registration.portrait)
    await message.answer("📸 Теперь отправьте ровно одну фотографию персонажа.")


@router.message(Registration.portrait, F.photo)
async def registration_portrait(message: Message, state: FSMContext) -> None:
    await state.update_data(portrait_file_id=message.photo[-1].file_id)
    await state.set_state(Registration.house_name)
    await message.answer("🏠 Введите название вашего дома.")


@router.message(Registration.portrait)
async def portrait_invalid(message: Message) -> None:
    await message.answer("Нужно отправить фотографию как изображение, а не файл или текст.")


@router.message(Registration.house_name)
async def registration_house_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not 2 <= len(name) <= 100:
        await message.answer("Название дома должно содержать от 2 до 100 символов.")
        return
    await state.update_data(house_name=name)
    await state.set_state(Registration.house_photo)
    await message.answer("🖼 Отправьте ровно одну фотографию дома.")


@router.message(Registration.house_photo, F.photo)
async def registration_house_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    settings = get_settings()
    user = User(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_admin=message.from_user.id in settings.admins,
    )
    character = Character(
        name=data["name"],
        portrait_file_id=data["portrait_file_id"],
    )
    character.house = House(
        name=data["house_name"],
        image_file_id=message.photo[-1].file_id,
    )
    user.character = character
    session.add(user)
    await session.flush()
    await state.clear()
    await message.answer(
        "✅ Персонаж и дом созданы. Вы получили 10 золотых.",
        reply_markup=main_menu(),
    )


@router.message(Registration.house_photo)
async def house_photo_invalid(message: Message) -> None:
    await message.answer("Нужно отправить фотографию дома как изображение.")
