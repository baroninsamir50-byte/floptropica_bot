from datetime import datetime, timedelta, timezone
from random import choice

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.keyboards import (
    admin_attack_players_keyboard,
    admin_extended_keyboard,
    admin_media_keyboard,
    admin_players_keyboard,
    admin_roles_keyboard,
    house_attack_keyboard,
)
from app.models import Character, GameEvent, House, HouseAttack, User
from app.services import (
    apply_levels,
    change_gold,
    get_character,
    set_system_media,
)
from app.states import AdminMediaUpload

router = Router()

ROLE_DATA = {
    "citizen": ("Гражданин", None),
    "leader_west": ("Лидер фракции «Западная сторона»", "Западная сторона"),
    "leader_neutral": ("Лидер фракции «Нейтральный Диалог»", "Нейтральный Диалог"),
    "king": ("Король", None),
    "queen": ("Королева", None),
    "princess": ("Королевна", None),
}

MEDIA_NAMES = {
    "shop": "магазина дня",
    "treasury": "казны",
    "development": "развития",
    "factions": "фракций",
    "map": "карты Королевства",
}


def is_admin(user_id: int) -> bool:
    return user_id in get_settings().admins


async def deny_callback(callback: CallbackQuery) -> bool:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return True
    return False


async def show_admin_home(message: Message) -> None:
    await message.answer(
        "⚙ <b>Панель создателя</b>\n\n"
        "Управление игроками, изображениями, домами и событиями.",
        reply_markup=admin_extended_keyboard(),
    )


@router.message(Command("admin"))
async def admin_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(
            "Недостаточно прав.\n"
            f"Ваш Telegram ID: <code>{message.from_user.id}</code>\n"
            "Добавьте его в переменную ADMIN_IDS на Render."
        )
        return
    await show_admin_home(message)


@router.callback_query(F.data == "admin:home")
async def admin_home(callback: CallbackQuery) -> None:
    if await deny_callback(callback):
        return
    await callback.answer()
    await callback.message.edit_text(
        "⚙ <b>Панель создателя</b>",
        reply_markup=admin_extended_keyboard(),
    )


@router.callback_query(F.data == "admin:players")
async def admin_players(callback: CallbackQuery, session: AsyncSession) -> None:
    if await deny_callback(callback):
        return
    result = await session.execute(
        select(User.telegram_id, Character.name, Character.title)
        .join(Character, Character.user_id == User.id)
        .order_by(Character.name)
    )
    players = list(result.all())
    await callback.answer()
    if not players:
        await callback.message.edit_text(
            "Зарегистрированных игроков пока нет.",
            reply_markup=admin_extended_keyboard(),
        )
        return
    await callback.message.edit_text(
        "👥 <b>Выберите игрока</b>",
        reply_markup=admin_players_keyboard(players),
    )


@router.callback_query(F.data.startswith("adminplayer:"))
async def admin_player(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if await deny_callback(callback):
        return
    telegram_id = int(callback.data.split(":", 1)[1])
    character = await get_character(session, telegram_id)
    if not character:
        await callback.answer("Игрок не найден.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        f"👤 <b>{character.name}</b>\n"
        f"Telegram ID: <code>{telegram_id}</code>\n"
        f"Роль: {character.title}\n"
        f"Фракция: {character.faction}\n\n"
        "Выберите новую роль:",
        reply_markup=admin_roles_keyboard(telegram_id),
    )


@router.callback_query(F.data.startswith("setrole:"))
async def set_role(callback: CallbackQuery, session: AsyncSession) -> None:
    if await deny_callback(callback):
        return
    _, telegram_id_raw, role_key = callback.data.split(":", 2)
    role = ROLE_DATA.get(role_key)
    if not role:
        await callback.answer("Неизвестная роль.", show_alert=True)
        return

    telegram_id = int(telegram_id_raw)
    character = await get_character(session, telegram_id)
    if not character:
        await callback.answer("Игрок не найден.", show_alert=True)
        return

    title, faction = role
    character.title = title
    if role_key == "citizen":
        character.faction = "Нет"
    elif faction:
        character.faction = faction

    await callback.answer("Роль назначена.", show_alert=True)
    await callback.message.edit_text(
        f"✅ Игроку <b>{character.name}</b> назначена роль:\n"
        f"<b>{title}</b>\n"
        f"Фракция: {character.faction}",
        reply_markup=admin_roles_keyboard(telegram_id),
    )


@router.callback_query(F.data == "admin:media")
async def admin_media_panel(callback: CallbackQuery) -> None:
    if await deny_callback(callback):
        return
    await callback.answer()
    await callback.message.edit_text(
        "🖼 <b>Изображения разделов</b>\n\n"
        "Выберите раздел, затем отправьте одну фотографию.",
        reply_markup=admin_media_keyboard(),
    )


@router.callback_query(F.data.startswith("adminmedia:"))
async def admin_media_request(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if await deny_callback(callback):
        return
    key = callback.data.split(":", 1)[1]
    if key not in MEDIA_NAMES:
        await callback.answer("Неизвестный раздел.", show_alert=True)
        return
    await state.set_state(AdminMediaUpload.photo)
    await state.update_data(media_key=key)
    await callback.answer()
    await callback.message.answer(
        f"📸 Отправьте новую фотографию для раздела "
        f"<b>{MEDIA_NAMES[key]}</b>."
    )


@router.message(AdminMediaUpload.photo, F.photo)
async def admin_media_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    key = data.get("media_key")
    if key not in MEDIA_NAMES:
        await state.clear()
        await message.answer("Не удалось определить раздел.")
        return

    await set_system_media(session, key, message.photo[-1].file_id)
    await state.clear()
    await message.answer(
        f"✅ Фотография раздела <b>{MEDIA_NAMES[key]}</b> обновлена.",
        reply_markup=admin_media_keyboard(),
    )


@router.message(AdminMediaUpload.photo)
async def admin_media_invalid(message: Message) -> None:
    await message.answer("Нужно отправить фотографию как изображение.")


@router.callback_query(F.data == "admin:attack_players")
async def admin_attack_players(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if await deny_callback(callback):
        return
    result = await session.execute(
        select(User.telegram_id, Character.name)
        .join(Character, Character.user_id == User.id)
        .order_by(Character.name)
    )
    players = list(result.all())
    await callback.answer()
    if not players:
        await callback.message.edit_text(
            "Зарегистрированных игроков пока нет.",
            reply_markup=admin_extended_keyboard(),
        )
        return
    await callback.message.edit_text(
        "🐉 <b>Выберите дом для тестового нападения</b>",
        reply_markup=admin_attack_players_keyboard(players),
    )


@router.callback_query(F.data.startswith("adminattack:"))
async def admin_force_attack(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if await deny_callback(callback):
        return

    telegram_id = int(callback.data.split(":", 1)[1])
    character = await get_character(session, telegram_id)
    if not character or not character.house:
        await callback.answer("Дом игрока не найден.", show_alert=True)
        return

    result = await session.execute(
        select(HouseAttack).where(
            HouseAttack.house_id == character.house.id,
            HouseAttack.status.in_(
                ["waiting", "player_fighting", "guards_fighting"]
            ),
        )
    )
    if result.scalars().first():
        await callback.answer(
            "На этот дом уже идёт нападение.",
            show_alert=True,
        )
        return

    enemy_name, enemy_type, base_power = choice([
        ("🐉 Дракон", "dragon", 44),
        ("👹 Болотный урод", "monster", 32),
        ("🌀 Аномалия", "anomaly", 40),
    ])
    attack = HouseAttack(
        house_id=character.house.id,
        enemy_name=enemy_name,
        enemy_type=enemy_type,
        enemy_power=base_power + character.level * 2,
        enemy_hp=60 + base_power + character.level * 2,
        response_deadline=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    session.add(attack)
    await session.flush()

    try:
        await callback.bot.send_message(
            telegram_id,
            f"⚠ <b>ТЕСТОВОЕ НАПАДЕНИЕ!</b>\n"
            f"{enemy_name} атакует ваш дом.",
            reply_markup=house_attack_keyboard(attack.id),
        )
    except Exception:
        pass

    await callback.answer("Нападение создано.", show_alert=True)


@router.callback_query(F.data == "admin:repair_all")
async def admin_repair_all(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if await deny_callback(callback):
        return
    result = await session.execute(select(House))
    houses = list(result.scalars())
    for house in houses:
        house.integrity = 100
    await callback.answer(
        f"Восстановлено домов: {len(houses)}",
        show_alert=True,
    )


@router.callback_query(F.data == "admin:stats")
async def admin_stats(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if await deny_callback(callback):
        return

    players_count = await session.scalar(
        select(func.count(Character.id))
    ) or 0
    houses_count = await session.scalar(
        select(func.count(House.id))
    ) or 0
    active_attacks = await session.scalar(
        select(func.count(HouseAttack.id)).where(
            HouseAttack.status.in_(
                ["waiting", "player_fighting", "guards_fighting"]
            )
        )
    ) or 0

    await callback.answer()
    await callback.message.edit_text(
        f"📊 <b>Статистика Королевства</b>\n\n"
        f"Игроков: {players_count}\n"
        f"Домов: {houses_count}\n"
        f"Активных нападений: {active_attacks}",
        reply_markup=admin_extended_keyboard(),
    )


@router.callback_query(F.data == "admin:event_help")
async def admin_event_help(callback: CallbackQuery) -> None:
    if await deny_callback(callback):
        return
    await callback.answer()
    await callback.message.edit_text(
        "Для запуска события используйте:\n"
        "<code>/запустить_событие Текст события</code>",
        reply_markup=admin_extended_keyboard(),
    )


async def find_character(
    session: AsyncSession,
    telegram_id: int,
) -> Character | None:
    result = await session.execute(
        select(Character)
        .join(User)
        .where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


@router.message(Command("дать_золото"))
async def give_gold(
    message: Message,
    session: AsyncSession,
) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Формат: /дать_золото TELEGRAM_ID AMOUNT")
        return

    try:
        telegram_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("ID и сумма должны быть числами.")
        return

    character = await find_character(session, telegram_id)
    if not character:
        await message.answer("Игрок не найден.")
        return

    try:
        await change_gold(
            session,
            character,
            amount,
            f"admin:{message.from_user.id}",
        )
        await message.answer(f"Готово. Баланс игрока: {character.gold}")
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command("дать_опыт"))
async def give_xp(
    message: Message,
    session: AsyncSession,
) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Формат: /дать_опыт TELEGRAM_ID AMOUNT")
        return

    try:
        telegram_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("ID и опыт должны быть числами.")
        return

    character = await find_character(session, telegram_id)
    if not character:
        await message.answer("Игрок не найден.")
        return

    character.experience += max(0, amount)
    levels = apply_levels(character)
    await message.answer(
        f"Готово. Уровень: {character.level}. "
        f"Повышений: {levels}."
    )


@router.message(Command("запустить_событие"))
async def launch_event(
    message: Message,
    session: AsyncSession,
) -> None:
    if not is_admin(message.from_user.id):
        return

    title = (message.text or "").partition(" ")[2].strip()
    if not title:
        await message.answer("Формат: /запустить_событие ТЕКСТ")
        return

    session.add(GameEvent(title=title))
    await message.answer(f"⚠ Событие запущено:\n\n{title}")
