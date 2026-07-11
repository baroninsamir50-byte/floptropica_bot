from datetime import datetime, timedelta, timezone
from random import randint

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards import (
    house_attack_keyboard, house_battle_keyboard, house_panel_keyboard,
    repair_house_keyboard,
)
from app.models import Character, HouseAttack, OwnedNpc
from app.services import apply_levels, get_character, get_effective_stats, percent_bonus

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


def integrity_label(value: int) -> str:
    if value >= 80:
        return "🟢 Надёжное"
    if value >= 50:
        return "🟡 Повреждённое"
    if value >= 20:
        return "🟠 Аварийное"
    return "🔴 На грани разрушения"


async def show_house_panel(target: Message, session: AsyncSession, telegram_id: int):
    char = await get_character(session, telegram_id)
    if not char or not char.house:
        await target.answer("Дом не найден. Сначала зарегистрируйтесь: /start")
        return
    attack = await active_attack(session, char.house.id)
    guard_total = await guards_count(session, char.id)
    attack_text = "Нет активной угрозы"
    if attack:
        statuses = {
            "waiting": "⚠ Ожидает вашего решения",
            "player_fighting": "⚔ Вы защищаете дом",
            "guards_fighting": "👮 Стража ведёт бой",
        }
        attack_text = f"{attack.enemy_name}: {statuses.get(attack.status, attack.status)}"
    await target.answer(
        f"🏰 <b>Панель владения: {char.house.name}</b>\n\n"
        f"🏗 Прочность: {char.house.integrity}/100 — {integrity_label(char.house.integrity)}\n"
        f"✨ Энергия ремонта: {char.house.repair_energy}\n"
        f"🛡 Постоянная защита: {char.house.defense}\n"
        f"👮 Стражники: {guard_total}\n"
        f"🐉 Угроза: {attack_text}\n\n"
        "Ежедневная угроза появляется после установленного часа. "
        "На ответ даётся 10 минут, затем стража действует автоматически.",
        reply_markup=house_panel_keyboard(attack.id if attack and attack.status == "waiting" else None),
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
    if missing <= 0:
        await callback.answer("Дом уже полностью восстановлен.", show_alert=True)
        return
    requested = callback.data.split(":", 1)[1]
    amount = min(missing, char.house.repair_energy)
    if requested != "max":
        amount = min(amount, int(requested))
    if amount <= 0:
        await callback.answer("Недостаточно энергии ремонта.", show_alert=True)
        return
    char.house.repair_energy -= amount
    char.house.integrity += amount
    await callback.answer(f"Восстановлено {amount} прочности.", show_alert=True)
    await callback.message.edit_text(
        f"✅ Дом отремонтирован.\n"
        f"Прочность: {char.house.integrity}/100\n"
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
        f"Использовано стражников: {attack.guards_used}"
    )


@router.callback_query(F.data.startswith("housefight:"))
async def start_personal_fight(callback: CallbackQuery, session: AsyncSession):
    attack = await session.get(HouseAttack, int(callback.data.split(":")[1]))
    char = await get_character(session, callback.from_user.id)
    if not char or not char.house or not attack or attack.house_id != char.house.id:
        await callback.answer("Это нападение относится к другому дому.", show_alert=True)
        return
    if attack.status not in {"waiting", "guards_fighting"}:
        await callback.answer("Нельзя начать этот бой.", show_alert=True)
        return
    if attack.status == "guards_fighting":
        await callback.answer("Стража уже вступила в бой.", show_alert=True)
        return
    stats = await get_effective_stats(session, char)
    attack.status = "player_fighting"
    attack.player_hp = stats["health"] + stats["endurance"] * 2 + char.level * 2
    attack.player_mana = stats["mana"] + stats["intelligence"]
    await callback.answer("Вы вступили в бой!")
    await callback.message.edit_text(
        f"⚔ <b>Оборона дома</b>\n\n"
        f"{char.name}: ❤️ {attack.player_hp} | 🔮 {attack.player_mana}\n"
        f"{attack.enemy_name}: ❤️ {attack.enemy_hp}\n\n"
        "Выберите действие:",
        reply_markup=house_battle_keyboard(attack.id),
    )


@router.callback_query(F.data.startswith("houseguards:"))
async def send_guards(callback: CallbackQuery, session: AsyncSession):
    attack = await session.get(HouseAttack, int(callback.data.split(":")[1]))
    char = await get_character(session, callback.from_user.id)
    if not char or not char.house or not attack or attack.house_id != char.house.id:
        await callback.answer("Недоступно.", show_alert=True)
        return
    if attack.status not in {"waiting", "player_fighting"}:
        await callback.answer("Стража уже действует или бой завершён.", show_alert=True)
        return
    count = await guards_count(session, char.id)
    if count <= 0:
        await callback.answer("У вас нет стражников.", show_alert=True)
        return
    attack.status = "guards_fighting"
    attack.guards_used = min(count, 4)
    hours = randint(2, 4)
    attack.guard_finish_at = datetime.now(timezone.utc) + timedelta(hours=hours)
    await callback.answer("Стража отправлена!", show_alert=True)
    await callback.message.edit_text(
        f"👮 Стража вступила в бой с {attack.enemy_name}.\n"
        f"Использовано стражников: {attack.guards_used}\n"
        f"Расчётное время боя: {hours} ч.\n\n"
        "Бот автоматически сообщит результат."
    )


@router.callback_query(F.data.startswith("houseact:"))
async def house_action(callback: CallbackQuery, session: AsyncSession):
    _, attack_id, action = callback.data.split(":", 2)
    attack = await session.get(HouseAttack, int(attack_id))
    char = await get_character(session, callback.from_user.id)
    if not char or not char.house or not attack or attack.house_id != char.house.id:
        await callback.answer("Недоступно.", show_alert=True)
        return
    if attack.status != "player_fighting":
        await callback.answer("Бой уже завершён или передан страже.", show_alert=True)
        return

    stats = await get_effective_stats(session, char)
    if action == "defend":
        attack.player_defending = True
        heal = max(1, stats["endurance"] // 4)
        attack.player_hp += heal
        log = f"🛡 Вы укрепляете оборону и восстанавливаете {heal} здоровья."
    else:
        enemy_evasion = min(5, max(1, attack.enemy_power // 20))
        hit = randint(1, 100) <= 92 - enemy_evasion
        if not hit:
            log = f"💨 {attack.enemy_name} уклоняется от удара."
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
                damage = randint(7, 13) + stats["strength"] + char.level // 2
                crit = randint(1, 100) <= 5 + min(5, stats["luck"] // 5)
                if crit:
                    damage = int(damage * 1.5)
                label = "критическую атаку" if crit else "силовую атаку"
            attack.enemy_hp = max(0, attack.enemy_hp - damage)
            log = f"💥 Вы применяете {label} и наносите {damage} урона."

    if attack.enemy_hp <= 0:
        attack.status = "player_won"
        attack.finished_at = datetime.now(timezone.utc)
        stat_name = "strength" if randint(0, 1) == 0 else "magic"
        setattr(char, stat_name, getattr(char, stat_name) + 1)
        energy = randint(12, 20)
        char.house.repair_energy += energy
        char.experience += 15
        apply_levels(char)
        await callback.answer()
        await callback.message.edit_text(
            f"🏆 <b>Дом защищён!</b>\n\n"
            f"Вы победили {attack.enemy_name}.\n"
            f"Получено: +1 к {'силе' if stat_name == 'strength' else 'магии'}, "
            f"{energy} энергии ремонта и 15 XP."
        )
        return

    # Ответ врага
    evade = percent_bonus(stats["agility"], attack.enemy_power // 3)
    if randint(1, 100) <= evade:
        enemy_log = f"💨 Ловкость помогла уклониться (+{evade}%)."
    else:
        damage = randint(7, 14) + attack.enemy_power // 8
        protection = percent_bonus(stats["endurance"], attack.enemy_power // 3)
        damage = max(1, int(damage * (100 - protection) / 100))
        if attack.player_defending:
            damage = max(1, damage // 2)
            attack.player_defending = False
        attack.player_hp = max(0, attack.player_hp - damage)
        enemy_log = f"🐲 Враг наносит {damage} урона. Выносливость снизила урон на {protection}%."

    if attack.player_hp <= 0:
        damage_house = randint(12, 28)
        char.house.integrity = max(0, char.house.integrity - damage_house)
        attack.damage_done = damage_house
        attack.status = "enemy_won"
        attack.finished_at = datetime.now(timezone.utc)
        await callback.answer()
        await callback.message.edit_text(
            f"💀 Вы проиграли бой. {attack.enemy_name} повреждает дом на {damage_house}.\n"
            f"Прочность дома: {char.house.integrity}/100."
        )
        return

    await callback.answer()
    await callback.message.edit_text(
        f"{log}\n{enemy_log}\n\n"
        f"⚔ <b>Оборона дома</b>\n"
        f"{char.name}: ❤️ {attack.player_hp} | 🔮 {attack.player_mana}\n"
        f"{attack.enemy_name}: ❤️ {attack.enemy_hp}",
        reply_markup=house_battle_keyboard(attack.id),
    )
