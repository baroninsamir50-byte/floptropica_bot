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


async def notify(bot: Bot, telegram_id: int, text: str, reply_markup=None):
    try:
        await bot.send_message(telegram_id, text, reply_markup=reply_markup)
    except Exception:
        # Пользователь мог заблокировать бота; игра продолжает работать.
        pass


async def create_daily_attacks(bot: Bot):
    settings = get_settings()
    if not settings.house_attacks_enabled:
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
            .where((House.last_attack_date.is_(None)) | (House.last_attack_date != today))
        )
        rows = list(result.all())
        for house, character, user in rows:
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
            await notify(
                bot,
                user.telegram_id,
                f"⚠ <b>НАПАДЕНИЕ НА ДОМ!</b>\n\n"
                f"{enemy_name} атакует <b>{house.name}</b>.\n"
                f"Сила угрозы: {power}\n"
                f"Прочность дома: {house.integrity}/100\n\n"
                "У вас есть 10 минут, чтобы вступить в бой или отправить стражу. "
                "Если вы не ответите, имеющиеся стражники выступят автоматически.",
                house_attack_keyboard(attack.id),
            )
        await session.commit()


async def resolve_expired_waiting(bot: Bot):
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        result = await session.execute(
            select(HouseAttack, House, Character, User)
            .join(House, House.id == HouseAttack.house_id)
            .join(Character, Character.id == House.owner_id)
            .join(User, User.id == Character.user_id)
            .where(
                HouseAttack.status == "waiting",
                HouseAttack.response_deadline <= now,
            )
        )
        for attack, house, character, user in result.all():
            guard_result = await session.execute(
                select(OwnedNpc.quantity).where(
                    OwnedNpc.character_id == character.id,
                    OwnedNpc.npc_type == "guard",
                )
            )
            guards = guard_result.scalar_one_or_none() or 0
            if guards > 0:
                attack.status = "guards_fighting"
                attack.guards_used = min(guards, 4)
                hours = randint(2, 4)
                attack.guard_finish_at = now + timedelta(hours=hours)
                await notify(
                    bot, user.telegram_id,
                    f"👮 Вы не ответили за 10 минут. "
                    f"{attack.guards_used} стражника автоматически вступили в бой "
                    f"с {attack.enemy_name}. Результат будет через {hours} ч."
                )
            else:
                damage = randint(18, 35)
                house.integrity = max(0, house.integrity - damage)
                attack.damage_done = damage
                attack.status = "enemy_won"
                attack.finished_at = now
                await notify(
                    bot, user.telegram_id,
                    f"💥 {attack.enemy_name} повредил дом на {damage}.\n"
                    f"Стражников не было.\nПрочность: {house.integrity}/100."
                )
        await session.commit()


async def resolve_guard_battles(bot: Bot):
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        result = await session.execute(
            select(HouseAttack, House, Character, User)
            .join(House, House.id == HouseAttack.house_id)
            .join(Character, Character.id == House.owner_id)
            .join(User, User.id == Character.user_id)
            .where(
                HouseAttack.status == "guards_fighting",
                HouseAttack.guard_finish_at <= now,
            )
        )
        for attack, house, character, user in result.all():
            chance = min(
                90,
                25 + attack.guards_used * 14 + house.defense // 2
                - max(0, attack.enemy_power - 30) // 2,
            )
            if randint(1, 100) <= max(10, chance):
                attack.status = "guards_won"
                attack.finished_at = now
                energy = randint(5, 10)
                house.repair_energy += energy
                await notify(
                    bot, user.telegram_id,
                    f"🏆 Стража победила {attack.enemy_name}!\n"
                    f"Шанс победы был {max(10, chance)}%.\n"
                    f"Дом не повреждён. Получено {energy} энергии ремонта."
                )
            else:
                damage = randint(8, 22)
                house.integrity = max(0, house.integrity - damage)
                attack.damage_done = damage
                attack.status = "guards_lost"
                attack.finished_at = now
                await notify(
                    bot, user.telegram_id,
                    f"⚠ Стража проиграла бой с {attack.enemy_name}.\n"
                    f"Дом получил {damage} урона. Прочность: {house.integrity}/100."
                )
        await session.commit()


async def process_due_game_tasks(bot: Bot) -> dict[str, str]:
    """
    Обрабатывает все игровые сроки на основании времени в PostgreSQL.

    Функцию безопасно вызывать:
    - при запуске;
    - из внутреннего цикла;
    - через защищённый HTTP endpoint;
    - несколько раз подряд.
    """
    async with _task_lock:
        await create_daily_attacks(bot)
        await resolve_expired_waiting(bot)
        await resolve_guard_battles(bot)
    return {"status": "ok", "processed_at": datetime.now(timezone.utc).isoformat()}


async def house_attack_loop(bot: Bot):
    while True:
        try:
            await process_due_game_tasks(bot)
        except Exception:
            # Ошибка одного цикла не должна останавливать Telegram-бота.
            pass
        await asyncio.sleep(60)
