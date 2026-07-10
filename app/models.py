from __future__ import annotations
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class EquipmentSlot(StrEnum):
    WEAPON = "weapon"
    ARMOR = "armor"
    AMULET = "amulet"
    PET = "pet"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(128))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    character: Mapped["Character"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    portrait_file_id: Mapped[str] = mapped_column(Text)
    level: Mapped[int] = mapped_column(Integer, default=1)
    experience: Mapped[int] = mapped_column(Integer, default=0)
    gold: Mapped[int] = mapped_column(Integer, default=10)
    health: Mapped[int] = mapped_column(Integer, default=100)
    mana: Mapped[int] = mapped_column(Integer, default=50)
    strength: Mapped[int] = mapped_column(Integer, default=5)
    intelligence: Mapped[int] = mapped_column(Integer, default=5)
    agility: Mapped[int] = mapped_column(Integer, default=5)
    magic: Mapped[int] = mapped_column(Integer, default=5)
    luck: Mapped[int] = mapped_column(Integer, default=5)
    endurance: Mapped[int] = mapped_column(Integer, default=5)
    charisma: Mapped[int] = mapped_column(Integer, default=5)
    reputation: Mapped[int] = mapped_column(Integer, default=0)
    profession: Mapped[str] = mapped_column(String(64), default="Без профессии")
    faction: Mapped[str] = mapped_column(String(64), default="Нет")
    social_status: Mapped[str] = mapped_column(String(64), default="Обычный житель")
    title: Mapped[str] = mapped_column(String(64), default="Гражданин")
    training_date: Mapped[str | None] = mapped_column(String(10))
    work_count_date: Mapped[str | None] = mapped_column(String(10))
    work_count: Mapped[int] = mapped_column(Integer, default=0)
    work_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    work_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    work_reward_claimed: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="character")
    house: Mapped["House"] = relationship(back_populates="owner", uselist=False, cascade="all, delete-orphan")
    inventory: Mapped[list["InventoryItem"]] = relationship(back_populates="character", cascade="all, delete-orphan")
    npcs: Mapped[list["OwnedNpc"]] = relationship(back_populates="character", cascade="all, delete-orphan")


class House(Base):
    __tablename__ = "houses"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    image_file_id: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(100), default="Неизвестные земли")
    description: Mapped[str] = mapped_column(Text, default="Личное владение гражданина.")
    level: Mapped[int] = mapped_column(Integer, default=1)
    value: Mapped[int] = mapped_column(Integer, default=100)
    defense: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(64), default="Жилой дом")

    owner: Mapped[Character] = relationship(back_populates="house")


class ItemTemplate(Base):
    __tablename__ = "item_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[int] = mapped_column(Integer)
    slot: Mapped[str | None] = mapped_column(String(16))
    rarity: Mapped[str] = mapped_column(String(32), default="Обычный")
    stat_name: Mapped[str | None] = mapped_column(String(32))
    stat_bonus: Mapped[int] = mapped_column(Integer, default=0)


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (UniqueConstraint("character_id", "item_id", name="uq_character_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item_templates.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    equipped: Mapped[bool] = mapped_column(Boolean, default=False)

    character: Mapped[Character] = relationship(back_populates="inventory")
    item: Mapped[ItemTemplate] = relationship()


class OwnedNpc(Base):
    __tablename__ = "owned_npcs"
    __table_args__ = (UniqueConstraint("character_id", "npc_type", name="uq_character_npc_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"))
    npc_type: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    last_income_date: Mapped[str | None] = mapped_column(String(10))

    character: Mapped[Character] = relationship(back_populates="npcs")


class GoldTransaction(Base):
    __tablename__ = "gold_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"))
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GameEvent(Base):
    __tablename__ = "game_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
