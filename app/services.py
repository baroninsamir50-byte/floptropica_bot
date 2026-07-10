from __future__ import annotations
from datetime import datetime, timedelta, timezone
from random import randint
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Character, GoldTransaction, InventoryItem, ItemTemplate, OwnedNpc, User


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
        select(Character).join(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def change_gold(session: AsyncSession, character: Character, amount: int, reason: str) -> None:
    if character.gold + amount < 0:
        raise ValueError("Недостаточно золота.")
    character.gold += amount
    session.add(GoldTransaction(character_id=character.id, amount=amount, reason=reason))


async def seed_items(session: AsyncSession) -> None:
    existing = await session.scalar(select(ItemTemplate.id).limit(1))
    if existing:
        return
    templates = [
        ItemTemplate(slug="iron_sword", name="Железный меч", description="+2 к силе", price=20, slot="weapon", rarity="Обычный", stat_name="strength", stat_bonus=2),
        ItemTemplate(slug="royal_armor", name="Королевская броня", description="+3 к выносливости", price=35, slot="armor", rarity="Необычный", stat_name="endurance", stat_bonus=3),
        ItemTemplate(slug="moon_amulet", name="Лунный амулет", description="+2 к магии", price=30, slot="amulet", rarity="Редкий", stat_name="magic", stat_bonus=2),
        ItemTemplate(slug="fox_pet", name="Лис Флоппи", description="+2 к удаче", price=40, slot="pet", rarity="Редкий", stat_name="luck", stat_bonus=2),
        ItemTemplate(slug="healing_potion", name="Зелье здоровья", description="Восстанавливает здоровье (расходник будет расширен позже)", price=8, slot=None, rarity="Обычный"),
    ]
    session.add_all(templates)
    await session.commit()


async def start_work(character: Character) -> str:
    now = datetime.now(timezone.utc)
    today = local_date()

    if character.work_ends_at and not character.work_reward_claimed:
        if now < character.work_ends_at:
            remaining = character.work_ends_at - now
            minutes = max(1, int(remaining.total_seconds() // 60))
            raise ValueError(f"Вы уже работаете. Осталось примерно {minutes} мин.")
        raise ValueError("Сначала получите награду командой /работа_статус.")

    if character.work_count_date != today:
        character.work_count_date = today
        character.work_count = 0

    if character.work_count >= 2:
        raise ValueError("Сегодня вы уже работали два раза.")

    character.work_count += 1
    character.work_started_at = now
    character.work_ends_at = now + timedelta(hours=2)
    character.work_reward_claimed = False
    return "Работа началась на 2 часа."


async def claim_work(session: AsyncSession, character: Character) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    if not character.work_ends_at or character.work_reward_claimed:
        raise ValueError("У вас нет завершённой работы.")
    if now < character.work_ends_at:
        remaining = character.work_ends_at - now
        minutes = max(1, int(remaining.total_seconds() // 60))
        raise ValueError(f"Работа ещё идёт. Осталось примерно {minutes} мин.")

    gold = randint(1, 5)
    xp = randint(5, 10)
    await change_gold(session, character, gold, "work_reward")
    character.experience += xp
    character.work_reward_claimed = True
    apply_levels(character)
    return gold, xp


async def buy_item(session: AsyncSession, character: Character, item_id: int) -> ItemTemplate:
    item = await session.get(ItemTemplate, item_id)
    if not item:
        raise ValueError("Предмет не найден.")
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
    amount = sum(randint(1, 2) for _ in range(peasants.quantity))
    peasants.last_income_date = today
    await change_gold(session, character, amount, "npc_daily_income")
    return amount
