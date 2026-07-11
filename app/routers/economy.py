from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards import inventory_keyboard, npc_keyboard, shop_keyboard
from app.models import InventoryItem, ItemTemplate, OwnedNpc
from app.services import (
    buy_item, buy_npc, claim_work, collect_npc_income, get_character,
    start_work, toggle_equip, get_daily_shop_items, get_system_media, local_date,
)

router = Router()


async def show_work(message: Message, session: AsyncSession, telegram_id: int) -> None:
    c = await get_character(session, telegram_id)
    if not c:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    try:
        text = await start_work(c)
        await message.answer(f"💼 {text}\nНаграда: 1–5 золота и 5–10 XP.")
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command("работа", "work"))
async def work(message: Message, session: AsyncSession) -> None:
    await show_work(message, session, message.from_user.id)


@router.callback_query(F.data == "menu:work")
async def work_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await show_work(callback.message, session, callback.from_user.id)


@router.message(Command("работа_статус", "work_status"))
async def work_status(message: Message, session: AsyncSession) -> None:
    c = await get_character(session, message.from_user.id)
    if not c:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    try:
        gold, xp = await claim_work(session, c)
        await message.answer(f"✅ Работа завершена. Получено {gold} золота и {xp} XP.")
    except ValueError as exc:
        await message.answer(str(exc))


async def show_shop(message: Message, session: AsyncSession) -> None:
    items = await get_daily_shop_items(session, 5)
    rows = [(item.id, item.name, item.price) for item in items]
    lines = ["🛒 <b>Королевский магазин</b>", f"📅 Ассортимент на {local_date()}", "", "Сегодня доступны 5 товаров:"]
    for item in items:
        lines.append(f"• <b>{item.name}</b> — {item.price} 🪙\n  {item.rarity}. {item.description}")
    lines.append("\nАссортимент сменится на следующие сутки.")
    file_id = await get_system_media(session, "shop")
    if file_id:
        await message.answer_photo(file_id, caption="\n".join(lines), reply_markup=shop_keyboard(rows))
    else:
        await message.answer("\n".join(lines), reply_markup=shop_keyboard(rows))


@router.message(Command("магазин", "shop"))
async def shop(message: Message, session: AsyncSession) -> None:
    await show_shop(message, session)


@router.callback_query(F.data == "menu:shop")
async def shop_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await show_shop(callback.message, session)


@router.callback_query(F.data.startswith("buy:"))
async def purchase(callback: CallbackQuery, session: AsyncSession) -> None:
    c = await get_character(session, callback.from_user.id)
    try:
        item = await buy_item(session, c, int(callback.data.split(":")[1]))
        await callback.answer(f"Куплено: {item.name}", show_alert=True)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)


async def show_inventory(message: Message, session: AsyncSession, telegram_id: int) -> None:
    c = await get_character(session, telegram_id)
    if not c:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    result = await session.execute(
        select(InventoryItem, ItemTemplate)
        .join(ItemTemplate, ItemTemplate.id == InventoryItem.item_id)
        .where(InventoryItem.character_id == c.id)
        .order_by(ItemTemplate.name)
    )
    rows = result.all()
    if not rows:
        await message.answer("🎒 Инвентарь пуст.")
        return
    lines = ["🎒 <b>Инвентарь</b>"]
    buttons = []
    for inv, item in rows:
        marker = "✅" if inv.equipped else "•"
        lines.append(f"{marker} {item.name} ×{inv.quantity} — {item.rarity}")
        buttons.append((inv.id, item.name, inv.equipped, item.slot))
    await message.answer("\n".join(lines), reply_markup=inventory_keyboard(buttons))


@router.message(Command("инвентарь", "экипировка", "inventory", "equipment"))
async def inventory(message: Message, session: AsyncSession) -> None:
    await show_inventory(message, session, message.from_user.id)


@router.callback_query(F.data == "menu:inventory")
async def inventory_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await show_inventory(callback.message, session, callback.from_user.id)


@router.callback_query(F.data.startswith("equip:"))
async def equip(callback: CallbackQuery, session: AsyncSession) -> None:
    c = await get_character(session, callback.from_user.id)
    try:
        name, equipped = await toggle_equip(session, c, int(callback.data.split(":")[1]))
        await callback.answer(
            f"{name}: {'экипировано' if equipped else 'снято'}",
            show_alert=True,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)


async def show_npc(message: Message, session: AsyncSession, telegram_id: int) -> None:
    c = await get_character(session, telegram_id)
    if not c:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    result = await session.execute(select(OwnedNpc).where(OwnedNpc.character_id == c.id))
    owned = {npc.npc_type: npc.quantity for npc in result.scalars()}
    text = (
        "🧑‍🌾 <b>Ваши NPC</b>\n"
        f"Крестьяне: {owned.get('peasant', 0)}\n"
        f"Стражники: {owned.get('guard', 0)}\n\n"
        "Каждый крестьянин приносит 1–2 золота в сутки."
    )
    await message.answer(text, reply_markup=npc_keyboard())


@router.message(Command("npc", "npcs"))
async def npcs(message: Message, session: AsyncSession) -> None:
    await show_npc(message, session, message.from_user.id)


@router.callback_query(F.data == "menu:npc")
async def npcs_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await show_npc(callback.message, session, callback.from_user.id)


@router.callback_query(F.data.startswith("npcbuy:"))
async def npc_purchase(callback: CallbackQuery, session: AsyncSession) -> None:
    c = await get_character(session, callback.from_user.id)
    try:
        name, price = await buy_npc(session, c, callback.data.split(":")[1])
        await callback.answer(f"Куплен {name} за {price} золота.", show_alert=True)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "npcincome")
async def npc_income(callback: CallbackQuery, session: AsyncSession) -> None:
    c = await get_character(session, callback.from_user.id)
    try:
        amount = await collect_npc_income(session, c)
        await callback.answer(f"Получено {amount} золота.", show_alert=True)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "treasury:claim")
async def treasury_claim(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    c = await get_character(session, callback.from_user.id)
    if not c:
        await callback.message.answer("Сначала зарегистрируйтесь: /start")
        return
    try:
        gold, xp = await claim_work(session, c)
        await callback.message.answer(f"✅ Работа завершена. Получено {gold} золота и {xp} XP.")
    except ValueError as exc:
        await callback.message.answer(str(exc))
