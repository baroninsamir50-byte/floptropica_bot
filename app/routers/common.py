from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("помощь"))
async def help_command(message: Message) -> None:
    await message.answer(
        "📜 <b>Команды Королевства</b>\n\n"
        "/меню — главное меню\n"
        "/профиль — карточка персонажа\n"
        "/дом — карточка дома\n"
        "/сменить_портрет — заменить одно фото персонажа\n"
        "/сменить_фото_дома — заменить одно фото дома\n"
        "/тренировка — ежедневная прокачка\n"
        "/работа — начать двухчасовую работу\n"
        "/работа_статус — получить награду\n"
        "/магазин — купить предмет\n"
        "/инвентарь — предметы и экипировка\n"
        "/профессии — выбрать профессию\n"
        "/фракции — выбрать фракцию\n"
        "/npc — управление NPC"
    )
