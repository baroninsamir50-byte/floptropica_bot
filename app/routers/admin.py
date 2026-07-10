from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Character, GameEvent, User
from app.services import apply_levels, change_gold

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in get_settings().admins


@router.message(Command("admin"))
async def admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return
    await message.answer(
        "⚙ <b>Админ-панель</b>\n\n"
        "/дать_золото TELEGRAM_ID AMOUNT\n"
        "/дать_опыт TELEGRAM_ID AMOUNT\n"
        "/запустить_событие ТЕКСТ"
    )


async def find_character(session: AsyncSession, telegram_id: int) -> Character | None:
    result = await session.execute(
        select(Character).join(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


@router.message(Command("дать_золото"))
async def give_gold(message: Message, session: AsyncSession) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Формат: /дать_золото TELEGRAM_ID AMOUNT")
        return
    try:
        telegram_id, amount = int(parts[1]), int(parts[2])
    except ValueError:
        await message.answer("ID и сумма должны быть числами.")
        return
    c = await find_character(session, telegram_id)
    if not c:
        await message.answer("Игрок не найден.")
        return
    try:
        await change_gold(session, c, amount, f"admin:{message.from_user.id}")
        await message.answer(f"Готово. Баланс игрока: {c.gold}")
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command("дать_опыт"))
async def give_xp(message: Message, session: AsyncSession) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Формат: /дать_опыт TELEGRAM_ID AMOUNT")
        return
    try:
        telegram_id, amount = int(parts[1]), int(parts[2])
    except ValueError:
        await message.answer("ID и опыт должны быть числами.")
        return
    c = await find_character(session, telegram_id)
    if not c:
        await message.answer("Игрок не найден.")
        return
    c.experience += max(0, amount)
    levels = apply_levels(c)
    await message.answer(f"Готово. Уровень: {c.level}. Повышений: {levels}.")


@router.message(Command("запустить_событие"))
async def launch_event(message: Message, session: AsyncSession) -> None:
    if not is_admin(message.from_user.id):
        return
    title = (message.text or "").partition(" ")[2].strip()
    if not title:
        await message.answer("Формат: /запустить_событие ТЕКСТ")
        return
    session.add(GameEvent(title=title))
    await message.answer(f"⚠ Событие запущено:\n\n{title}")
