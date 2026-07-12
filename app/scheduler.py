import asyncio
from datetime import datetime, timedelta, timezone
from random import choice, randint
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionFactory
from app.keyboards import house_attack_keyboard
from app.models import Character, House, HouseAttack, OwnedNpc, User

_task_lock = asyncio.Lock()

ENEMIES = [
    ("🐉 Молодой дракон", "dragon", 42),
    ("👹 Болотный урод", "monster", 30),
    ("🌀 Живая аномалия", "anomaly", 38),
    ("🧟 Отряд проклятых", "undead", 34),
    ("🔥 Огненный бес", "demon", 36),
]


async def send_group(bot: Bot, text: str, reply_markup=None):
    chat_id = get_settings().game_chat_id
    if not chat_id:
        return
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception:
        pass


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
            enemy_name, enemy_type, base_power = choice(ENEMIES)
            power = base_power + character.level * 2 + randint(-4, 8)
            attack = HouseAttack(
                house_id=house.id,
                enemy_name=enemy_name,
                enemy_type=enemy_type,
                enemy_power=power,
                enemy_hp=55 + power,
                response_deadline=now + timedelta(minutes=10),
            )
            house.last_attack_date = today
            session.add(attack)
            await session.flush()

            mention = (
                f"@{user.username}" if user.username
                else f'<a href="tg://user?id={user.telegram_id}">{character.name}</a>'
            )
            await send_group(
                bot,
                f"⚠ <b>НАПАДЕНИЕ НА ВЛАДЕНИЕ!</b>\n\n"
                f"{enemy_name} атакует <b>{house.name}</b>.\n"
                f"Владелец: {mention}\n"
                f"Сила угрозы: {power}\n"
                f"Прочность дома: {house.integrity}/100\n\n"
                "Владелец может защитить дом лично или отправить стражу. "
                "Любой зарегистрированный гражданин может прийти на помощь.\n\n"
                "Если дом спасёт друг, помощник получит очки развития, "
                "но владение всё равно потеряет 10 прочности.",
                house_attack_keyboard(attack.id),
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
            guard_result = await session.execute(
                select(OwnedNpc.quantity).where(
                    OwnedNpc.character_id == owner.id,
                    OwnedNpc.npc_type == "guard",
                )
            )
            guards = guard_result.scalar_one_or_none() or 0
            if guards > 0:
                attack.status = "guards_fighting"
                attack.guards_used = min(guards, 4)
                hours = randint(2, 4)
                attack.guard_finish_at = now + timedelta(hours=hours)
                await send_group(
                    bot,
                    f"👮 Владелец и друзья не вступили в бой вовремя.\n"
                    f"{attack.guards_used} стражника автоматически защищают "
                    f"<b>{house.name}</b> от {attack.enemy_name}.\n"
                    f"Результат будет через {hours} ч."
                )
            else:
                damage = randint(18, 35)
                house.integrity = max(0, house.integrity - damage)
                attack.damage_done = damage
                attack.status = "enemy_won"
                attack.finished_at = now
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
            select(HouseAttack, House)
            .join(House, House.id == HouseAttack.house_id)
            .where(
                HouseAttack.status == "guards_fighting",
                HouseAttack.guard_finish_at <= now,
            )
        )
        for attack, house in result.all():
            chance = min(
                90,
                25 + attack.guards_used * 14 + house.defense // 2
                - max(0, attack.enemy_power - 30) // 2,
            )
            chance = max(10, chance)
            if randint(1, 100) <= chance:
                attack.status = "guards_won"
                attack.finished_at = now
                energy = randint(5, 10)
                house.repair_energy += energy
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
                await send_group(
                    bot,
                    f"⚠ Стража <b>{house.name}</b> проиграла бой.\n"
                    f"Дом получает {damage} урона.\n"
                    f"Прочность: {house.integrity}/100."
                )
        await session.commit()


async def process_due_game_tasks(bot: Bot) -> dict[str, str]:
    async with _task_lock:
        await create_daily_attacks(bot)
        await resolve_expired_waiting(bot)
        await resolve_guard_battles(bot)
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
