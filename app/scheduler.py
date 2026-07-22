import asyncio
from datetime import datetime, timedelta, timezone
from random import choice, randint
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select

from app.config import get_settings
from app.database import SessionFactory
from app.models import Character, House, HouseAttack, NpcUnit, User, Farm, FarmPlot, FarmStock, FarmMarketListing
from app.services import npc_power
from app.farm_events import CROPS

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
                    NpcUnit.fatigue < 90,
                    NpcUnit.hunger < 90,
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
                    guard.hunger = min(100, guard.hunger + 8)

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
                recovery = 60 if npc.assignment == "rest_long" else 35
                npc.fatigue = max(0, npc.fatigue - recovery)
                npc.exhaustion_started_at = None
                npc.last_rest_at = now
            elif npc.status == "training":
                npc.level += 1
                npc.experience = 0
            npc.status = "idle"
            npc.assignment = None
            npc.available_at = None

        vitals_result = await session.execute(
            select(NpcUnit).where(NpcUnit.alive.is_(True))
        )
        for npc in vitals_result.scalars():
            updated = npc.hunger_updated_at or now
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            elapsed = max(0, int((now - updated).total_seconds()))
            hunger_points = elapsed // (3 * 60 * 60)
            if hunger_points:
                npc.hunger = min(100, npc.hunger + hunger_points)
                npc.hunger_updated_at = updated + timedelta(hours=hunger_points * 3)
            if npc.fatigue >= 100:
                npc.exhaustion_started_at = npc.exhaustion_started_at or now
            else:
                npc.exhaustion_started_at = None
            if npc.hunger >= 100:
                npc.starvation_started_at = npc.starvation_started_at or now
            else:
                npc.starvation_started_at = None
            if npc.status == "resting":
                continue
            exhausted_at = npc.exhaustion_started_at
            starving_at = npc.starvation_started_at
            if exhausted_at and exhausted_at.tzinfo is None:
                exhausted_at = exhausted_at.replace(tzinfo=timezone.utc)
            if starving_at and starving_at.tzinfo is None:
                starving_at = starving_at.replace(tzinfo=timezone.utc)
            if (exhausted_at and now - exhausted_at >= timedelta(hours=24)) or (
                starving_at and now - starving_at >= timedelta(hours=24)
            ):
                npc.alive = False
                npc.status = "dead"
        await session.commit()


async def process_farms():
    """Автополив, автосбор и питание NPC из амбара."""
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        farms_result = await session.execute(select(Farm))
        for farm in farms_result.scalars():
            house = await session.get(House, farm.house_id)
            if not house:
                continue
            owner = await session.get(Character, house.owner_id)
            if not owner:
                continue
            member_ids = [owner.id]
            if owner.spouse_character_id:
                spouse = await session.get(Character, owner.spouse_character_id)
                if spouse and spouse.spouse_character_id == owner.id:
                    member_ids.append(spouse.id)

            stock_result = await session.execute(
                select(FarmStock).where(FarmStock.farm_id == farm.id)
            )
            stock_rows = list(stock_result.scalars())
            stock_map = {row.crop_slug: row for row in stock_rows if row.quantity > 0}

            if farm.auto_feed and stock_map:
                hungry_result = await session.execute(
                    select(NpcUnit).where(
                        NpcUnit.character_id.in_(member_ids),
                        NpcUnit.alive.is_(True),
                        NpcUnit.hunger >= 70,
                    ).order_by(NpcUnit.hunger.desc())
                )
                crop_order = sorted(
                    CROPS, key=lambda slug: int(CROPS[slug]["hunger_restore"]), reverse=True
                )
                for npc in hungry_result.scalars():
                    while npc.hunger >= 50:
                        slug = next(
                            (item for item in crop_order if item in stock_map and stock_map[item].quantity > 0),
                            None,
                        )
                        if not slug:
                            break
                        row = stock_map[slug]
                        row.quantity -= 1
                        npc.hunger = max(0, npc.hunger - int(CROPS[slug]["hunger_restore"]))
                        npc.starvation_started_at = None
                        if row.quantity <= 0:
                            await session.delete(row)
                            stock_map.pop(slug, None)

            if not farm.farmer_npc_id:
                continue
            farmer = await session.get(NpcUnit, farm.farmer_npc_id)
            if (
                not farmer or not farmer.alive or farmer.npc_type != "peasant"
                or farmer.character_id not in member_ids
            ):
                farm.farmer_npc_id = None
                continue
            if farmer.status not in {"idle", "working"} or farmer.fatigue >= 90 or farmer.hunger >= 90:
                continue

            plots_result = await session.execute(
                select(FarmPlot).where(FarmPlot.farm_id == farm.id).order_by(FarmPlot.slot)
            )
            active = [plot for plot in plots_result.scalars() if plot.crop_slug]
            capacity = min(3, 2 + max(0, farmer.skill - 20) // 20)
            for plot in active[:capacity]:
                if farmer.fatigue >= 90 or farmer.hunger >= 90:
                    break
                water_due = plot.water_due_at
                ready_at = plot.ready_at
                if water_due and water_due.tzinfo is None:
                    water_due = water_due.replace(tzinfo=timezone.utc)
                if ready_at and ready_at.tzinfo is None:
                    ready_at = ready_at.replace(tzinfo=timezone.utc)
                if not plot.watered_at and water_due and now >= water_due:
                    plot.watered_at = now
                    farmer.fatigue = min(100, farmer.fatigue + 4)
                    farmer.hunger = min(100, farmer.hunger + 2)
                    farmer.experience += 2
                if plot.watered_at and ready_at and now >= ready_at and plot.crop_slug in CROPS:
                    current_used = await session.scalar(
                        select(func.coalesce(func.sum(FarmStock.quantity), 0)).where(FarmStock.farm_id == farm.id)
                    )
                    free = max(0, farm.barn_capacity - int(current_used or 0))
                    amount = min(free, int(CROPS[plot.crop_slug]["yield"]))
                    if amount <= 0:
                        break
                    row = await session.scalar(
                        select(FarmStock).where(
                            FarmStock.farm_id == farm.id, FarmStock.crop_slug == plot.crop_slug
                        )
                    )
                    if row:
                        row.quantity += amount
                    else:
                        session.add(FarmStock(farm_id=farm.id, crop_slug=plot.crop_slug, quantity=amount))
                    plot.crop_slug = None
                    plot.planted_at = None
                    plot.water_due_at = None
                    plot.watered_at = None
                    plot.ready_at = None
                    farmer.fatigue = min(100, farmer.fatigue + 6)
                    farmer.hunger = min(100, farmer.hunger + 4)
                    farmer.experience += 4 + farmer.level
        await session.commit()


async def return_expired_market_listings():
    """Возвращает непроданный урожай в амбар после 24 часов."""
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        result = await session.execute(
            select(FarmMarketListing).where(
                FarmMarketListing.status.in_(["active", "return_pending"]),
                FarmMarketListing.expires_at <= now,
            ).order_by(FarmMarketListing.id)
        )
        for listing in result.scalars():
            seller = await session.get(Character, listing.seller_character_id)
            if not seller:
                listing.status = "expired_returned"
                continue
            member_ids = [seller.id]
            if seller.spouse_character_id:
                spouse = await session.get(Character, seller.spouse_character_id)
                if spouse and spouse.spouse_character_id == seller.id:
                    member_ids.append(spouse.id)
            houses_result = await session.execute(
                select(House).where(House.owner_id.in_(member_ids)).order_by(House.owner_id)
            )
            houses = list(houses_result.scalars())
            if not houses:
                listing.status = "expired_returned"
                continue
            farm = await session.scalar(select(Farm).where(Farm.house_id == houses[0].id))
            if not farm:
                listing.status = "expired_returned"
                continue
            used = int(await session.scalar(
                select(func.coalesce(func.sum(FarmStock.quantity), 0)).where(FarmStock.farm_id == farm.id)
            ) or 0)
            returned = min(max(0, farm.barn_capacity - used), listing.quantity)
            if returned > 0:
                stock = await session.scalar(select(FarmStock).where(
                    FarmStock.farm_id == farm.id,
                    FarmStock.crop_slug == listing.crop_slug,
                ))
                if stock:
                    stock.quantity += returned
                else:
                    session.add(FarmStock(farm_id=farm.id, crop_slug=listing.crop_slug, quantity=returned))
                listing.quantity -= returned
            listing.status = "expired_returned" if listing.quantity <= 0 else "return_pending"
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
        await process_farms()
        await return_expired_market_listings()
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
