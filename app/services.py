from __future__ import annotations
from datetime import datetime, timedelta, timezone
from random import Random, randint
import hashlib
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import Character, GoldTransaction, InventoryItem, ItemTemplate, OwnedNpc, SystemMedia, User
from app.work_catalog import profession_by_name, title_can_use


def local_date() -> str:
    return datetime.now(ZoneInfo(get_settings().timezone)).date().isoformat()


def xp_for_next(level: int) -> int:
    return 50 * level * level + 50 * level


def apply_levels(character: Character) -> int:
    levels = 0
    while character.experience >= xp_for_next(character.level):
        character.experience -= xp_for_next(character.level)
        character.level += 1
        character.health += 10
        character.mana += 5
        levels += 1
    return levels


async def get_character(session: AsyncSession, telegram_id: int) -> Character | None:
    result = await session.execute(
        select(Character).join(User).options(selectinload(Character.house)).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def change_gold(session: AsyncSession, character: Character, amount: int, reason: str) -> None:
    if character.gold + amount < 0:
        raise ValueError("Недостаточно золота.")
    character.gold += amount
    session.add(GoldTransaction(character_id=character.id, amount=amount, reason=reason))


async def seed_items(session: AsyncSession) -> None:
    catalog = [
        ("development_points_30", "Свиток развития +30",
         "Даёт 30 свободных очков развития. Можно купить один раз в сутки.",
         45, None, "Мифический", None, 0),
        ("iron_sword", "Железный меч", "+2 к силе", 20, "weapon", "Обычный", "strength", 2),
        ("knight_blade", "Клинок рыцаря", "+4 к силе", 45, "weapon", "Необычный", "strength", 4),
        ("mage_staff", "Посох мага", "+5 к магии", 60, "weapon", "Редкий", "magic", 5),
        ("leather_armor", "Кожаная броня", "+2 к выносливости", 24, "armor", "Обычный", "endurance", 2),
        ("royal_armor", "Королевская броня", "+4 к выносливости", 50, "armor", "Необычный", "endurance", 4),
        ("dragon_armor", "Броня драконьей чешуи", "+7 к выносливости", 95, "armor", "Эпический", "endurance", 7),
        ("moon_amulet", "Лунный амулет", "+3 к магии", 35, "amulet", "Редкий", "magic", 3),
        ("luck_amulet", "Амулет удачи", "+4 к удаче", 42, "amulet", "Редкий", "luck", 4),
        ("heart_amulet", "Амулет живого сердца", "+15 к здоровью", 55, "amulet", "Эпический", "health", 15),
        ("fox_pet", "Лис Флоппи", "+2 к удаче", 40, "pet", "Редкий", "luck", 2),
        ("owl_pet", "Королевская сова", "+3 к интеллекту", 48, "pet", "Редкий", "intelligence", 3),
        ("guardian_cat", "Кот-страж", "+3 к выносливости", 52, "pet", "Эпический", "endurance", 3),
        ("healing_potion", "Зелье здоровья", "+10 к запасу здоровья", 8, None, "Обычный", "health", 10),
        ("greater_healing_potion", "Большое зелье здоровья", "+25 к запасу здоровья", 18, None, "Необычный", "health", 25),
        ("mana_crystal", "Кристалл маны", "+15 к запасу маны", 16, None, "Необычный", "mana", 15),
    ]
    result = await session.execute(select(ItemTemplate))
    existing = {x.slug: x for x in result.scalars().all()}
    for slug,name,description,price,slot,rarity,stat_name,stat_bonus in catalog:
        item = existing.get(slug)
        values = dict(name=name, description=description, price=price, slot=slot, rarity=rarity, stat_name=stat_name, stat_bonus=stat_bonus)
        if item:
            for k,v in values.items(): setattr(item,k,v)
        else:
            session.add(ItemTemplate(slug=slug, **values))
    await session.commit()


async def get_daily_shop_items(session: AsyncSession, count: int = 5) -> list[ItemTemplate]:
    result = await session.execute(select(ItemTemplate).order_by(ItemTemplate.slug))
    items = list(result.scalars().all())
    special = next((x for x in items if x.slug == "development_points_30"), None)
    regular = [x for x in items if x.slug != "development_points_30"]
    seed = int.from_bytes(
        hashlib.sha256(f"shop:{local_date()}".encode()).digest()[:8], "big"
    )
    selected = Random(seed).sample(regular, min(max(count - 1, 0), len(regular)))
    return ([special] if special else []) + selected


async def start_work(character: Character, profession: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    today = local_date()
    if character.work_ends_at and not character.work_reward_claimed:
        if now < character.work_ends_at:
            minutes = max(1, int((character.work_ends_at - now).total_seconds() // 60))
            raise ValueError(f"Вы уже работаете. Осталось примерно {minutes} мин.")
        raise ValueError("Сначала получите награду в Казне.")
    if character.work_count_date != today:
        character.work_count_date, character.work_count = today, 0
    if character.work_count >= 2:
        raise ValueError("Сегодня вы уже отработали две смены.")
    selected = profession or character.profession
    profession_data = profession_by_name(selected)
    if not profession_data:
        raise ValueError("Сначала выберите профессию в разделе Казна.")
    if not title_can_use(character.title, profession_data):
        raise ValueError("Эта профессия недоступна для вашей текущей роли.")
    character.profession = selected
    character.work_profession = selected
    character.work_count += 1
    character.work_started_at = now
    character.work_ends_at = now + timedelta(hours=2)
    character.work_reward_claimed = False
    return f"Смена «{selected}» началась на 2 часа."


async def claim_work(session: AsyncSession, character: Character) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    if not character.work_ends_at or character.work_reward_claimed:
        raise ValueError("У вас нет завершённой работы.")
    if now < character.work_ends_at:
        remaining = character.work_ends_at - now
        minutes = max(1, int(remaining.total_seconds() // 60))
        raise ValueError(f"Работа ещё идёт. Осталось примерно {minutes} мин.")

    profession = character.work_profession or character.profession
    profession_data = profession_by_name(profession)
    if profession_data:
        gold_range = profession_data["gold"]
        xp_range = profession_data["xp"]
        bonus_stat = profession_data.get("bonus_stat")
    else:
        gold_range, xp_range, bonus_stat = (1, 5), (5, 10), None
    multiplier = level_income_multiplier(character.level)
    gold = max(1, int(randint(*gold_range) * multiplier))
    xp = randint(*xp_range) + character.level // 3
    await change_gold(session, character, gold, f"work_reward:{profession}")
    character.experience += xp
    if bonus_stat and randint(1, 100) <= 20:
        setattr(character, bonus_stat, getattr(character, bonus_stat) + 1)
    character.work_reward_claimed = True
    apply_levels(character)
    return gold, xp


async def buy_item(session: AsyncSession, character: Character, item_id: int) -> ItemTemplate:
    item = await session.get(ItemTemplate, item_id)
    if not item:
        raise ValueError("Предмет не найден.")
    daily_items = await get_daily_shop_items(session)
    if item.id not in {x.id for x in daily_items}:
        raise ValueError("Сегодня этого предмета уже нет в магазине.")

    if item.slug == "development_points_30":
        today = local_date()
        if character.development_pack_date == today:
            raise ValueError("Сегодня вы уже покупали свиток развития.")
        await change_gold(session, character, -item.price, "buy:development_points_30")
        character.development_points += 30
        character.development_pack_date = today
        return item

    await change_gold(session, character, -item.price, f"buy:{item.slug}")
    result = await session.execute(
        select(InventoryItem).where(
            InventoryItem.character_id == character.id,
            InventoryItem.item_id == item.id,
        )
    )
    inventory_item = result.scalar_one_or_none()
    if inventory_item:
        inventory_item.quantity += 1
    else:
        session.add(InventoryItem(character_id=character.id, item_id=item.id, quantity=1))
    return item


async def toggle_equip(session: AsyncSession, character: Character, inventory_id: int) -> tuple[str, bool]:
    inv = await session.get(InventoryItem, inventory_id)
    if not inv or inv.character_id != character.id:
        raise ValueError("Предмет не найден.")
    item = await session.get(ItemTemplate, inv.item_id)
    if not item or not item.slot:
        raise ValueError("Этот предмет нельзя экипировать.")

    if inv.equipped:
        inv.equipped = False
        return item.name, False

    result = await session.execute(
        select(InventoryItem)
        .join(ItemTemplate, ItemTemplate.id == InventoryItem.item_id)
        .where(
            InventoryItem.character_id == character.id,
            InventoryItem.equipped.is_(True),
            ItemTemplate.slot == item.slot,
        )
    )
    for equipped_item in result.scalars():
        equipped_item.equipped = False
    inv.equipped = True
    return item.name, True


async def buy_npc(session: AsyncSession, character: Character, npc_type: str) -> tuple[str, int]:
    data = {
        "peasant": ("Крестьянин", 100),
        "guard": ("Стражник", 160),
    }
    if npc_type not in data:
        raise ValueError("Неизвестный NPC.")
    name, price = data[npc_type]
    await change_gold(session, character, -price, f"buy_npc:{npc_type}")

    result = await session.execute(
        select(OwnedNpc).where(
            OwnedNpc.character_id == character.id,
            OwnedNpc.npc_type == npc_type,
        )
    )
    owned = result.scalar_one_or_none()
    if owned:
        owned.quantity += 1
    else:
        session.add(OwnedNpc(character_id=character.id, npc_type=npc_type, quantity=1))
    return name, price


async def collect_npc_income(session: AsyncSession, character: Character) -> int:
    today = local_date()
    result = await session.execute(
        select(OwnedNpc).where(
            OwnedNpc.character_id == character.id,
            OwnedNpc.npc_type == "peasant",
        )
    )
    peasants = result.scalar_one_or_none()
    if not peasants or peasants.quantity <= 0:
        raise ValueError("У вас нет крестьян.")
    if peasants.last_income_date == today:
        raise ValueError("Сегодня доход уже собран.")
    base_amount = sum(randint(1, 2) for _ in range(peasants.quantity))
    amount = max(1, int(base_amount * level_income_multiplier(character.level)))
    peasants.last_income_date = today
    await change_gold(session, character, amount, "npc_daily_income")
    return amount




async def get_equipment_bonuses(
    session: AsyncSession,
    character_id: int,
) -> dict[str, int]:
    """Возвращает суммарные бонусы надетой экипировки персонажа."""
    result = await session.execute(
        select(ItemTemplate)
        .join(InventoryItem, InventoryItem.item_id == ItemTemplate.id)
        .where(
            InventoryItem.character_id == character_id,
            InventoryItem.equipped.is_(True),
        )
    )
    bonuses: dict[str, int] = {}
    for item in result.scalars():
        if item.stat_name:
            bonuses[item.stat_name] = (
                bonuses.get(item.stat_name, 0) + item.stat_bonus
            )
    return bonuses


async def get_effective_stats(session: AsyncSession, character: Character) -> dict[str, int]:
    bonuses = await get_equipment_bonuses(session, character.id)
    names = (
        "health", "mana", "strength", "intelligence", "agility",
        "magic", "luck", "endurance", "charisma",
    )
    return {
        name: max(0, int(getattr(character, name)) + bonuses.get(name, 0))
        for name in names
    }


def percent_bonus(value: int, opponent_value: int) -> int:
    """Преимущество характеристики даёт от 1 до 5 процентов."""
    difference = value - opponent_value
    if difference <= 0:
        return 0
    return min(5, max(1, difference // 3 + 1))


async def get_system_media(session: AsyncSession, key: str) -> str | None:
    result = await session.execute(select(SystemMedia.file_id).where(SystemMedia.key == key))
    return result.scalar_one_or_none()


async def set_system_media(session: AsyncSession, key: str, file_id: str) -> None:
    result = await session.execute(select(SystemMedia).where(SystemMedia.key == key))
    media = result.scalar_one_or_none()
    if media:
        media.file_id = file_id
    else:
        session.add(SystemMedia(key=key, file_id=file_id))



def level_income_multiplier(level: int) -> float:
    """Каждый уровень даёт +5% дохода, максимум +100%."""
    return 1.0 + min(max(level - 1, 0), 20) * 0.05


def level_rank(level: int) -> str:
    if level >= 30:
        return "Легенда Флоптропики"
    if level >= 20:
        return "Королевский герой"
    if level >= 15:
        return "Магистр Королевства"
    if level >= 10:
        return "Знатный гражданин"
    if level >= 5:
        return "Опытный гражданин"
    return "Начинающий гражданин"


async def claim_daily_reward(
    session: AsyncSession,
    character: Character,
) -> tuple[int, int, int]:
    today = local_date()
    if character.daily_reward_date == today:
        raise ValueError("Ежедневный подарок уже получен.")

    local_today = datetime.now(ZoneInfo(get_settings().timezone)).date()
    yesterday = (local_today - timedelta(days=1)).isoformat()
    if character.daily_reward_date == yesterday:
        character.login_streak += 1
    else:
        character.login_streak = 1

    multiplier = level_income_multiplier(character.level)
    gold = max(1, int((2 + min(character.login_streak, 7)) * multiplier))
    xp = 5 + min(character.login_streak, 7) * 2
    development = 5 if character.login_streak % 7 == 0 else 0

    await change_gold(session, character, gold, "daily_reward")
    character.experience += xp
    character.development_points += development
    character.daily_reward_date = today
    apply_levels(character)
    return gold, xp, development
