from datetime import datetime, timedelta, timezone
from random import randint

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards import (
    house_battle_keyboard,
    house_panel_keyboard,
    repair_house_keyboard,
)
from app.models import Character, House, HouseAttack, OwnedNpc
from app.services import (
    apply_levels,
    change_gold,
    get_character,
    get_effective_stats,
    percent_bonus,
)

router = Router()


async def active_attack(session: AsyncSession, house_id: int) -> HouseAttack | None:
    result = await session.execute(
        select(HouseAttack).where(
            HouseAttack.house_id == house_id,
            HouseAttack.status.in_(["waiting", "player_fighting", "guards_fighting"]),
        ).order_by(HouseAttack.id.desc())
    )
    return result.scalars().first()


async def guards_count(session: AsyncSession, character_id: int) -> int:
    result = await session.execute(
        select(OwnedNpc.quantity).where(
            OwnedNpc.character_id == character_id,
            OwnedNpc.npc_type == "guard",
        )
    )
    return result.scalar_one_or_none() or 0


async def owner_for_attack(
    session: AsyncSession,
    attack: HouseAttack,
) -> tuple[House, Character] | tuple[None, None]:
    house = await session.get(House, attack.house_id)
    if not house:
        return None, None
    owner = await session.get(Character, house.owner_id)
    return house, owner


def integrity_label(value: int) -> str:
    if value >= 80:
        return "🟢 Надёжное"
    if value >= 50:
        return "🟡 Повреждённое"
    if value >= 20:
        return "🟠 Аварийное"
    return "🔴 На грани разрушения"


async def show_house_panel(
    target: Message,
    session: AsyncSession,
    telegram_id: int,
):
    char = await get_character(session, telegram_id)
    if not char or not char.house:
        await target.answer("Дом не найден. Сначала зарегистрируйтесь: /start")
        return
    attack = await active_attack(session, char.house.id)
    guard_total = await guards_count(session, char.id)
    attack_text = "Нет активной угрозы"
    if attack:
        attack_text = f"{attack.enemy_name}: {attack.status}"
    await target.answer(
        f"🏰 <b>Панель владения: {char.house.name}</b>\n\n"
        f"🏗 Прочность: {char.house.integrity}/100 — {integrity_label(char.house.integrity)}\n"
        f"✨ Энергия ремонта: {char.house.repair_energy}\n"
        f"🛡 Постоянная защита: {char.house.defense}\n"
        f"👮 Стражники: {guard_total}\n"
        f"🐉 Угроза: {attack_text}\n\n"
        "Нападения публикуются в общем игровом чате. "
        "Дом может защищать владелец или другой гражданин.",
        reply_markup=house_panel_keyboard(),
    )


@router.message(Command("defense", "защита"))
async def defense_command(message: Message, session: AsyncSession):
    await show_house_panel(message, session, message.from_user.id)


@router.callback_query(F.data == "house:defense")
async def defense_callback(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    await show_house_panel(callback.message, session, callback.from_user.id)


@router.callback_query(F.data == "house:repair")
async def repair_menu(callback: CallbackQuery, session: AsyncSession):
    char = await get_character(session, callback.from_user.id)
    if not char or not char.house:
        await callback.answer("Дом не найден.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        f"🔧 <b>Мастерская дома</b>\n"
        f"Прочность: {char.house.integrity}/100\n"
        f"Энергия ремонта: {char.house.repair_energy}\n\n"
        "1 единица энергии восстанавливает 1 единицу прочности.",
        reply_markup=repair_house_keyboard(),
    )


@router.callback_query(F.data.startswith("houserepair:"))
async def repair_house(callback: CallbackQuery, session: AsyncSession):
    char = await get_character(session, callback.from_user.id)
    if not char or not char.house:
        await callback.answer("Дом не найден.", show_alert=True)
        return
    missing = 100 - char.house.integrity
    requested = callback.data.split(":", 1)[1]
    amount = min(missing, char.house.repair_energy)
    if requested != "max":
        amount = min(amount, int(requested))
    if amount <= 0:
        await callback.answer("Ремонт сейчас невозможен.", show_alert=True)
        return
    char.house.repair_energy -= amount
    char.house.integrity += amount
    await callback.answer(f"Восстановлено {amount}.", show_alert=True)
    await callback.message.edit_text(
        f"✅ Прочность дома: {char.house.integrity}/100\n"
        f"Осталось энергии: {char.house.repair_energy}",
        reply_markup=repair_house_keyboard(),
    )


@router.callback_query(F.data == "house:last_attack")
async def last_attack(callback: CallbackQuery, session: AsyncSession):
    char = await get_character(session, callback.from_user.id)
    if not char or not char.house:
        await callback.answer("Дом не найден.", show_alert=True)
        return
    result = await session.execute(
        select(HouseAttack).where(HouseAttack.house_id == char.house.id)
        .order_by(HouseAttack.id.desc()).limit(1)
    )
    attack = result.scalar_one_or_none()
    await callback.answer()
    if not attack:
        await callback.message.answer("История нападений пока пуста.")
        return
    await callback.message.answer(
        f"📜 <b>Последнее нападение</b>\n"
        f"Враг: {attack.enemy_name}\n"
        f"Статус: {attack.status}\n"
        f"Урон дому: {attack.damage_done}\n"
        f"Помощь друга: {'да' if attack.helped_by_friend else 'нет'}"
    )


async def begin_fight(
    callback: CallbackQuery,
    session: AsyncSession,
    helper_mode: bool,
):
    attack_id = int(callback.data.split(":")[1])
    attack = await session.get(HouseAttack, attack_id)
    defender = await get_character(session, callback.from_user.id)
    if not attack or not defender:
        await callback.answer("Бой недоступен.", show_alert=True)
        return
    house, owner = await owner_for_attack(session, attack)
    if not house or not owner:
        await callback.answer("Владение не найдено.", show_alert=True)
        return
    if attack.status != "waiting":
        await callback.answer("Другой защитник уже вступил в бой.", show_alert=True)
        return

    is_owner = defender.id == owner.id
    if helper_mode and is_owner:
        await callback.answer("Вы владелец — используйте кнопку владельца.", show_alert=True)
        return
    if not helper_mode and not is_owner:
        await callback.answer("Эта кнопка предназначена владельцу дома.", show_alert=True)
        return

    stats = await get_effective_stats(session, defender)
    attack.status = "player_fighting"
    attack.defender_character_id = defender.id
    attack.helped_by_friend = not is_owner
    attack.player_hp = stats["health"] + stats["endurance"] * 2 + defender.level * 2
    attack.player_mana = stats["mana"] + stats["intelligence"]
    await callback.answer("Вы вступили в бой!")
    await callback.message.edit_text(
        f"⚔ <b>Оборона владения «{house.name}»</b>\n\n"
        f"Защитник: <b>{defender.name}</b>\n"
        f"❤️ {attack.player_hp} | 🔮 {attack.player_mana}\n"
        f"{attack.enemy_name}: ❤️ {attack.enemy_hp}\n\n"
        + (
            "🤝 Дом защищает друг. Даже при победе владение потеряет 10 прочности."
            if attack.helped_by_friend else
            "🏰 Владелец лично защищает своё владение."
        ),
        reply_markup=house_battle_keyboard(attack.id),
    )


@router.callback_query(F.data.startswith("housefight:"))
async def owner_fight(callback: CallbackQuery, session: AsyncSession):
    await begin_fight(callback, session, helper_mode=False)


@router.callback_query(F.data.startswith("househelp:"))
async def helper_fight(callback: CallbackQuery, session: AsyncSession):
    await begin_fight(callback, session, helper_mode=True)


@router.callback_query(F.data.startswith("houseguards:"))
async def send_guards(callback: CallbackQuery, session: AsyncSession):
    attack = await session.get(HouseAttack, int(callback.data.split(":")[1]))
    char = await get_character(session, callback.from_user.id)
    if not attack or not char:
        await callback.answer("Недоступно.", show_alert=True)
        return
    house, owner = await owner_for_attack(session, attack)
    if not owner or char.id != owner.id:
        await callback.answer("Стражу может отправить только владелец.", show_alert=True)
        return
    if attack.status != "waiting":
        await callback.answer("Бой уже начался.", show_alert=True)
        return
    count = await guards_count(session, owner.id)
    if count <= 0:
        await callback.answer("У вас нет стражников.", show_alert=True)
        return
    attack.status = "guards_fighting"
    attack.guards_used = min(count, 4)
    hours = randint(2, 4)
    attack.guard_finish_at = datetime.now(timezone.utc) + timedelta(hours=hours)
    await callback.answer("Стража отправлена!", show_alert=True)
    await callback.message.edit_text(
        f"👮 {attack.guards_used} стражника защищают «{house.name}».\n"
        f"Результат боя будет через {hours} ч."
    )


@router.callback_query(F.data.startswith("houseact:"))
async def house_action(callback: CallbackQuery, session: AsyncSession):
    _, attack_id, action = callback.data.split(":", 2)
    attack = await session.get(HouseAttack, int(attack_id))
    defender = await get_character(session, callback.from_user.id)
    if not attack or not defender or attack.defender_character_id != defender.id:
        await callback.answer("Сейчас сражается другой игрок.", show_alert=True)
        return
    if attack.status != "player_fighting":
        await callback.answer("Бой уже завершён.", show_alert=True)
        return

    house, owner = await owner_for_attack(session, attack)
    stats = await get_effective_stats(session, defender)

    if action == "defend":
        attack.player_defending = True
        heal = max(1, stats["endurance"] // 4)
        attack.player_hp += heal
        player_log = f"🛡 Защитник восстанавливает {heal} здоровья."
    else:
        if action == "magic":
            cost = max(6, 12 - min(5, stats["intelligence"] // 8))
            if attack.player_mana < cost:
                await callback.answer(f"Нужно {cost} маны.", show_alert=True)
                return
            attack.player_mana -= cost
            damage = randint(9, 15) + stats["magic"] + stats["intelligence"] // 3
            label = "магический удар"
        else:
            damage = randint(7, 13) + stats["strength"] + defender.level // 2
            crit = randint(1, 100) <= 5 + min(10, stats["luck"] // 4)
            if crit:
                damage = int(damage * 1.5)
            label = "критическую атаку" if crit else "силовую атаку"
        attack.enemy_hp = max(0, attack.enemy_hp - damage)
        player_log = f"💥 {defender.name} применяет {label}: {damage} урона."

    if attack.enemy_hp <= 0:
        attack.status = "friend_won" if attack.helped_by_friend else "owner_won"
        attack.finished_at = datetime.now(timezone.utc)
        if attack.helped_by_friend:
            house.integrity = max(0, house.integrity - 10)
            attack.damage_done = 10
            defender.development_points += 10
            defender.experience += 25
            await change_gold(session, defender, 3, "friend_house_defense")
            reward = (
                "🤝 Друг спас владение и получает 10 очков развития, "
                "25 XP и 3 золота.\n"
                f"Дом теряет 10 прочности: {house.integrity}/100."
            )
        else:
            energy = randint(12, 20)
            house.repair_energy += energy
            defender.experience += 20
            reward = f"🏰 Владелец получает {energy} энергии ремонта и 20 XP."
        apply_levels(defender)
        await callback.answer()
        await callback.message.edit_text(
            f"🏆 <b>{defender.name} побеждает {attack.enemy_name}!</b>\n\n{reward}"
        )
        return

    evade = percent_bonus(stats["agility"], attack.enemy_power // 3)
    if randint(1, 100) <= evade:
        enemy_log = f"💨 Ловкость помогает уклониться (+{evade}%)."
    else:
        damage = randint(7, 14) + attack.enemy_power // 8
        protection = percent_bonus(stats["endurance"], attack.enemy_power // 3)
        damage = max(1, int(damage * (100 - protection) / 100))
        if attack.player_defending:
            damage = max(1, damage // 2)
            attack.player_defending = False
        attack.player_hp = max(0, attack.player_hp - damage)
        enemy_log = f"🐲 Враг наносит {damage} урона."

    if attack.player_hp <= 0:
        damage_house = randint(15, 30)
        house.integrity = max(0, house.integrity - damage_house)
        attack.damage_done = damage_house
        attack.status = "enemy_won"
        attack.finished_at = datetime.now(timezone.utc)
        await callback.answer()
        await callback.message.edit_text(
            f"💀 Защитник проиграл. Дом получает {damage_house} урона.\n"
            f"Прочность: {house.integrity}/100."
        )
        return

    await callback.answer()
    await callback.message.edit_text(
        f"{player_log}\n{enemy_log}\n\n"
        f"⚔ <b>Оборона «{house.name}»</b>\n"
        f"{defender.name}: ❤️ {attack.player_hp} | 🔮 {attack.player_mana}\n"
        f"{attack.enemy_name}: ❤️ {attack.enemy_hp}",
        reply_markup=house_battle_keyboard(attack.id),
    )
