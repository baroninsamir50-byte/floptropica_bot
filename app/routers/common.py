from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.services import claim_daily_reward, get_character
router=Router()

@router.message(Command("ping"))
async def ping(message:Message):
    await message.answer("🏓 Бот работает в этом чате.")

@router.message(Command("myid"))
async def myid(message:Message):
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")

@router.message(Command("help","помощь"))
async def help_command(message:Message):
    await message.answer(
        "📜 <b>Команды v5.0</b>\n"
        "/menu /profile /house /map /shop /work /work_status\n"
        "/games /duel /expedition /ping /myid"
    )



@router.message(Command("daily", "подарок"))
async def daily_reward_command(message: Message, session: AsyncSession):
    character = await get_character(session, message.from_user.id)
    if not character:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    try:
        gold, xp, development = await claim_daily_reward(session, character)
        extra = f" и {development} очков развития" if development else ""
        await message.answer(
            f"🎁 Получено {gold} золота, {xp} XP{extra}.\n"
            f"Серия входов: {character.login_streak} дн."
        )
    except ValueError as exc:
        await message.answer(str(exc))



@router.message(Command("chatid"))
async def chat_id_command(message: Message):
    await message.answer(
        f"ID этого чата: <code>{message.chat.id}</code>\n"
        "Добавьте это значение в переменную GAME_CHAT_ID на Render."
    )
