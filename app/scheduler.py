import asyncio
from datetime import datetime, timedelta, timezone
from random import choice, randint
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionFactory
from app.models import Character, House, HouseAttack, NpcUnit, User
from app.services import npc_power

_task_lock = asyncio.Lock()

ENEMIES = [
    ("🐉 Молодой дракон", "dragon", 42),
    ("👹 Болотный урод", "monster", 30),
    ("🌀 Живая аномалия", "anomaly", 38),
    ("🧟 Отряд проклятых", "monster", 34),
    ("🔥 Огненный бес", "monster", 36),
]


async def send_group(bot: Bot, text: str, reply_markup=None):
    chat_id = get_settings().game_chat_id
    if not chat_id:
        return
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception:
        pass


async def attack_keyboard(bot: Bot, attack_id: int):
    me = await bot.get_me()
    url = f"https://t.me/{me.username}?startapp=attack_{attack_id}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚔ Открыть бой в Mini App", url=url)
    ]])


async def create_daily_attacks(bot: Bot):
    settings = get_settings()
    if not settings.house_attacks_enabled or not settings.game_chat_id:
        return

    local_now = datetime.now(ZoneInfo(settings.timezone))
    if local_now.hour < settings.house_attack_hour:
        return

    today = local_now.date().isoformat()
    now = datetime.now(timezone.utc)

    async with SessionFactory() as session:
        result = await session.execute(
            select(House, Character, User)
            .join(Character, Character.id == House.owner_id)
            .join(User, User.id == Character.user_id)
            .where(
                (House.last_attack_date.is_(None))
                | (House.last_attack_date != today)
            )
        )
        for house, character, user in result.all():
            spouse = await session.get(Character, character.spouse_character_id) if character.spouse_character_id else None
            if spouse and spouse.spouse_character_id == character.id and character.id > spouse.id:
                continue
            household_level = max(character.level, spouse.level) if spouse else character.level
            enemy_name, enemy_type, base_power = choice(ENEMIES)
            power = (
                base_power
                + household_level * 2
                + house.threat_level * 5
                + randint(-3, 7)
            )
            attack = HouseAttack(
                house_id=house.id,
                enemy_name=enemy_name,
                enemy_type=enemy_type,
                enemy_power=power,
                enemy_hp=60 + power * 2,
                response_deadline=now + timedelta(minutes=10),
            )
            house.last_attack_date = today
            session.add(attack)
            await session.flush()

            mention = (
                f"@{user.username}" if user.username
                else f'<a href="tg://user?id={user.telegram_id}">{character.name}</a>'
            )
            if spouse:
                spouse_user = await session.get(User, spouse.user_id)
                spouse_mention = (
                    f"@{spouse_user.username}" if spouse_user and spouse_user.username
                    else f'<a href="tg://user?id={spouse_user.telegram_id}">{spouse.name}</a>' if spouse_user
                    else spouse.name
                )
                mention = f"{mention} и {spouse_mention}"
            await send_group(
                bot,
                f"⚠ <b>НАПАДЕНИЕ НА ВЛАДЕНИЕ!</b>\n\n"
                f"{enemy_name} атакует <b>{house.name}</b>.\n"
                f"Владелец: {mention}\n"
                f"Сила угрозы: {power}\n"
                f"Уровень угрозы владения: {house.threat_level}\n"
                f"Прочность дома: {house.integrity}/100\n\n"
                "У владельца есть 10 минут, чтобы открыть Mini App и вступить в бой. "
                "Если ответа не будет, свободные стражники начнут сражение автоматически.",
                await attack_keyboard(bot, attack.id),
            )
        await session.commit()


async def resolve_expired_waiting(bot: Bot):
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        result = await session.execute(
            select(HouseAttack, House, Character)
            .join(House, House.id == HouseAttack.house_id)
            .join(Character, Character.id == House.owner_id)
            .where(
                HouseAttack.status == "waiting",
                HouseAttack.response_deadline <= now,
            )
        )
        for attack, house, owner in result.all():
            spouse = await session.get(Character, owner.spouse_character_id) if owner.spouse_character_id else None
            household_ids = [owner.id] + ([spouse.id] if spouse and spouse.spouse_character_id == owner.id else [])
            guard_result = await session.execute(
                select(NpcUnit).where(
                    NpcUnit.character_id.in_(household_ids),
                    NpcUnit.npc_type == "guard",
                    NpcUnit.alive.is_(True),
                    NpcUnit.status == "idle",
                ).order_by(NpcUnit.level.desc(), NpcUnit.id)
            )
            guards = list(guard_result.scalars())
            if guards:
                used = guards[:8]
                attack.status = "guards_fighting"
                attack.guards_used = len(used)
                minutes = max(5, round(30 - (len(used) - 1) * 3.5))
                avg_level = sum(g.level for g in used) / len(used)
                minutes = max(4, round(minutes - max(0, avg_level - 1) * 1.5))
                attack.guard_finish_at = now + timedelta(minutes=minutes)
                for guard in used:
                    guard.status = "fighting"
                    guard.assignment = f"attack:{attack.id}"
                    guard.available_at = attack.guard_finish_at
                    guard.fatigue = min(100, guard.fatigue + 18)

                await send_group(
                    bot,
                    f"👮 Владелец не ответил вовремя.\n"
                    f"{len(used)} стражника автоматически защищают <b>{house.name}</b>.\n"
                    f"Расчётное время боя: {minutes} мин."
                )
            else:
                damage = randint(18, 35)
                house.integrity = max(0, house.integrity - damage)
                attack.damage_done = damage
                attack.status = "enemy_won"
                attack.finished_at = now
                house.threat_level += 1
                await send_group(
                    bot,
                    f"💥 Никто не защитил <b>{house.name}</b>.\n"
                    f"{attack.enemy_name} наносит {damage} урона.\n"
                    f"Прочность: {house.integrity}/100."
                )
        await session.commit()


async def resolve_guard_battles(bot: Bot):
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        result = await session.execute(
            select(HouseAttack, House, Character)
            .join(House, House.id == HouseAttack.house_id)
            .join(Character, Character.id == House.owner_id)
            .where(
                HouseAttack.status == "guards_fighting",
                HouseAttack.guard_finish_at <= now,
            )
        )
        for attack, house, owner in result.all():
            spouse = await session.get(Character, owner.spouse_character_id) if owner.spouse_character_id else None
            household_ids = [owner.id] + ([spouse.id] if spouse and spouse.spouse_character_id == owner.id else [])
            guard_result = await session.execute(
                select(NpcUnit).where(
                    NpcUnit.character_id.in_(household_ids),
                    NpcUnit.npc_type == "guard",
                    NpcUnit.assignment == f"attack:{attack.id}",
                    NpcUnit.alive.is_(True),
                )
            )
            guards = list(guard_result.scalars())
            avg_level = (
                sum(g.level for g in guards) / len(guards)
                if guards else 1
            )
            avg_power = (
                sum(npc_power(g) for g in guards) / len(guards)
                if guards else 10
            )
            chance = min(
                94,
                22
                + len(guards) * 9
                + int(avg_level * 2)
                + int(avg_power / 7)
                + house.defense // 2
                - max(0, attack.enemy_power - 35) // 2,
            )
            chance = max(8, chance)

            for guard in guards:
                guard.status = "idle"
                guard.assignment = None
                guard.available_at = None
                guard.experience += 10 + attack.enemy_power // 10
                guard.strength += 1
                guard.endurance += 1

            if randint(1, 100) <= chance:
                attack.status = "guards_won"
                attack.finished_at = now
                energy = randint(5, 10)
                house.repair_energy += energy
                house.threat_level += 1
                await send_group(
                    bot,
                    f"🏆 Стража владения <b>{house.name}</b> побеждает "
                    f"{attack.enemy_name}!\n"
                    f"Шанс победы: {chance}%.\n"
                    f"Получено {energy} энергии ремонта."
                )
            else:
                damage = randint(8, 22)
                house.integrity = max(0, house.integrity - damage)
                attack.damage_done = damage
                attack.status = "guards_lost"
                attack.finished_at = now
                house.threat_level += 1
                await send_group(
                    bot,
                    f"⚠ Стража <b>{house.name}</b> проиграла бой.\n"
                    f"Дом получает {damage} урона.\n"
                    f"Прочность: {house.integrity}/100."
                )
        await session.commit()


async def finish_npc_tasks():
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        result = await session.execute(
            select(NpcUnit).where(
                NpcUnit.alive.is_(True),
                NpcUnit.available_at.is_not(None),
                NpcUnit.available_at <= now,
                NpcUnit.status.in_(["working", "resting", "training"]),
            )
        )
        for npc in result.scalars():
            if npc.status == "resting":
                npc.fatigue = max(0, npc.fatigue - 70)
                npc.last_rest_at = now
            elif npc.status == "training":
                npc.level += 1
                npc.experience = 0
            npc.status = "idle"
            npc.assignment = None
            npc.available_at = None

        exhausted_result = await session.execute(
            select(NpcUnit).where(
                NpcUnit.npc_type == "peasant",
                NpcUnit.alive.is_(True),
                NpcUnit.fatigue >= 100,
                NpcUnit.status != "resting",
            )
        )
        for npc in exhausted_result.scalars():
            reference = npc.last_rest_at or npc.created_at
            if reference and now - reference >= timedelta(hours=24):
                npc.alive = False
                npc.status = "dead"
        await session.commit()


async def apply_cleaning_penalties():
    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.timezone)).date().isoformat()
    async with SessionFactory() as session:
        result = await session.execute(select(House))
        for house in result.scalars():
            if house.last_cleaning_penalty_date == today:
                continue
            if house.last_cleaning_date != today:
                house.cleanliness = max(0, house.cleanliness - 20)
                if house.cleanliness <= 40:
                    house.integrity = max(0, house.integrity - 3)
            house.last_cleaning_penalty_date = today
        await session.commit()


async def process_due_game_tasks(bot: Bot) -> dict[str, str]:
    async with _task_lock:
        await create_daily_attacks(bot)
        await resolve_expired_waiting(bot)
        await resolve_guard_battles(bot)
        await finish_npc_tasks()
        await apply_cleaning_penalties()
    return {
        "status": "ok",
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


async def house_attack_loop(bot: Bot):
    while True:
        try:
            await process_due_game_tasks(bot)
        except Exception:
            pass
        await asyncio.sleep(60)
