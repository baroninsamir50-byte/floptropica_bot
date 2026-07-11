from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
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
