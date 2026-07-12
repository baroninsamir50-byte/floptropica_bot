from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from app.config import get_settings
router=Router()

@router.message(Command("app","play","играть"))
async def open_miniapp(message:Message):
    settings=get_settings()
    if not settings.webapp_url:
        await message.answer("Mini App ещё не настроено создателем.")
        return
    url=settings.webapp_url.rstrip("/")+"/miniapp"
    await message.answer("👑 Откройте визуальное Королевство:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎮 Открыть Королевство",web_app=WebAppInfo(url=url))
        ]]))
