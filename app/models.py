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
    current_view: Mapped[str] = mapped_column(String(40), default="Вне Mini App")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    development_points: Mapped[int] = mapped_column(Integer, default=100)
    reputation: Mapped[int] = mapped_column(Integer, default=0)
    profession: Mapped[str] = mapped_column(String(64), default="Без профессии")
    faction: Mapped[str] = mapped_column(String(64), default="Не назначена")
    social_status: Mapped[str] = mapped_column(String(64), default="Обычный житель")
    spouse_character_id: Mapped[int | None] = mapped_column(ForeignKey("characters.id"), index=True)
    summer_guard_claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_npc_material_date: Mapped[str | None] = mapped_column(String(10))
    title_reward_date: Mapped[str | None] = mapped_column(String(10))
    story_reader_achievement_claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[str] = mapped_column(String(64), default="Жители")
    training_date: Mapped[str | None] = mapped_column(String(10))
    work_count_date: Mapped[str | None] = mapped_column(String(10))
    work_count: Mapped[int] = mapped_column(Integer, default=0)
    work_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    work_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    work_reward_claimed: Mapped[bool] = mapped_column(Boolean, default=True)
    work_profession: Mapped[str | None] = mapped_column(String(100))
    development_pack_date: Mapped[str | None] = mapped_column(String(10))
    daily_reward_date: Mapped[str | None] = mapped_column(String(10))
    login_streak: Mapped[int] = mapped_column(Integer, default=0)
    duel_rating: Mapped[int] = mapped_column(Integer, default=1000)
    duel_wins: Mapped[int] = mapped_column(Integer, default=0)
    duel_losses: Mapped[int] = mapped_column(Integer, default=0)
    duel_win_streak: Mapped[int] = mapped_column(Integer, default=0)

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
    integrity: Mapped[int] = mapped_column(Integer, default=100)
    repair_energy: Mapped[int] = mapped_column(Integer, default=0)
    last_attack_date: Mapped[str | None] = mapped_column(String(10))
    last_cleaning_date: Mapped[str | None] = mapped_column(String(10))
    cleanliness: Mapped[int] = mapped_column(Integer, default=100)
    threat_level: Mapped[int] = mapped_column(Integer, default=1)
    last_cleaning_penalty_date: Mapped[str | None] = mapped_column(String(10))

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


class Duel(Base):
    __tablename__ = "duels"
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    challenger_id: Mapped[int] = mapped_column(ForeignKey("characters.id"))
    opponent_id: Mapped[int] = mapped_column(ForeignKey("characters.id"))
    status: Mapped[str] = mapped_column(String(24), default="invited", index=True)
    turn_character_id: Mapped[int | None] = mapped_column(ForeignKey("characters.id"))
    challenger_hp: Mapped[int] = mapped_column(Integer, default=100)
    opponent_hp: Mapped[int] = mapped_column(Integer, default=100)
    challenger_mana: Mapped[int] = mapped_column(Integer, default=50)
    opponent_mana: Mapped[int] = mapped_column(Integer, default=50)
    challenger_defending: Mapped[bool] = mapped_column(Boolean, default=False)
    opponent_defending: Mapped[bool] = mapped_column(Boolean, default=False)
    challenger_dodging: Mapped[bool] = mapped_column(Boolean, default=False)
    opponent_dodging: Mapped[bool] = mapped_column(Boolean, default=False)
    challenger_stamina: Mapped[int] = mapped_column(Integer, default=100)
    opponent_stamina: Mapped[int] = mapped_column(Integer, default=100)
    challenger_style: Mapped[str] = mapped_column(String(24), default="guardian")
    opponent_style: Mapped[str] = mapped_column(String(24), default="guardian")
    challenger_potion_used: Mapped[bool] = mapped_column(Boolean, default=False)
    opponent_potion_used: Mapped[bool] = mapped_column(Boolean, default=False)
    round_number: Mapped[int] = mapped_column(Integer, default=1)
    battle_log: Mapped[str] = mapped_column(Text, default="[]")
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("characters.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Expedition(Base):
    __tablename__ = "expeditions"
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    host_character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"))
    status: Mapped[str] = mapped_column(String(24), default="lobby", index=True)
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    max_rounds: Mapped[int] = mapped_column(Integer, default=5)
    party_hp: Mapped[int] = mapped_column(Integer, default=100)
    treasure: Mapped[int] = mapped_column(Integer, default=0)
    party_mana: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExpeditionMember(Base):
    __tablename__ = "expedition_members"
    __table_args__ = (UniqueConstraint("expedition_id", "character_id", name="uq_expedition_member"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    expedition_id: Mapped[int] = mapped_column(ForeignKey("expeditions.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="Искатель")


class ExpeditionVote(Base):
    __tablename__ = "expedition_votes"
    __table_args__ = (UniqueConstraint("expedition_id", "round_number", "character_id", name="uq_expedition_round_vote"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    expedition_id: Mapped[int] = mapped_column(ForeignKey("expeditions.id", ondelete="CASCADE"), index=True)
    round_number: Mapped[int] = mapped_column(Integer)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"))
    choice: Mapped[str] = mapped_column(String(32))



class HouseAttack(Base):
    __tablename__ = "house_attacks"

    id: Mapped[int] = mapped_column(primary_key=True)
    house_id: Mapped[int] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    enemy_name: Mapped[str] = mapped_column(String(80))
    enemy_type: Mapped[str] = mapped_column(String(32))
    enemy_power: Mapped[int] = mapped_column(Integer)
    enemy_hp: Mapped[int] = mapped_column(Integer)
    player_hp: Mapped[int | None] = mapped_column(Integer)
    player_mana: Mapped[int | None] = mapped_column(Integer)
    player_defending: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="waiting", index=True)
    response_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    guard_finish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    guards_used: Mapped[int] = mapped_column(Integer, default=0)
    damage_done: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    defender_character_id: Mapped[int | None] = mapped_column(ForeignKey("characters.id"))
    helped_by_friend: Mapped[bool] = mapped_column(Boolean, default=False)


class SystemMedia(Base):
    __tablename__ = "system_media"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    file_id: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)




class HouseRoom(Base):
    __tablename__ = "house_rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    house_id: Mapped[int] = mapped_column(
        ForeignKey("houses.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    image_file_id: Mapped[str | None] = mapped_column(Text)
    cleanliness: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NpcUnit(Base):
    __tablename__ = "npc_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    npc_type: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(80))
    model_variant: Mapped[int] = mapped_column(Integer, default=1)
    level: Mapped[int] = mapped_column(Integer, default=1)
    upgrade_count: Mapped[int] = mapped_column(Integer, default=0)
    experience: Mapped[int] = mapped_column(Integer, default=0)
    strength: Mapped[int] = mapped_column(Integer, default=5)
    endurance: Mapped[int] = mapped_column(Integer, default=5)
    agility: Mapped[int] = mapped_column(Integer, default=5)
    skill: Mapped[int] = mapped_column(Integer, default=5)
    fatigue: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="idle", index=True)
    assignment: Mapped[str | None] = mapped_column(String(40))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_rest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alive: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PlayerStory(Base):
    __tablename__ = "player_stories"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), unique=True, index=True
    )
    introduction: Mapped[str] = mapped_column(Text)
    main_part_one: Mapped[str] = mapped_column(Text)
    main_part_two: Mapped[str] = mapped_column(Text)
    ending: Mapped[str] = mapped_column(Text)
    introduction_image_file_id: Mapped[str | None] = mapped_column(Text)
    main_part_one_image_file_id: Mapped[str | None] = mapped_column(Text)
    main_part_two_image_file_id: Mapped[str | None] = mapped_column(Text)
    ending_image_file_id: Mapped[str | None] = mapped_column(Text)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StoryRead(Base):
    __tablename__ = "story_reads"
    __table_args__ = (
        UniqueConstraint("reader_character_id", "story_character_id", name="uq_story_reader_author"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reader_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    story_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TarotCard(Base):
    __tablename__ = "tarot_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100))
    suit: Mapped[str] = mapped_column(String(64), default="Авторская карта")
    number: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    upright_meaning: Mapped[str] = mapped_column(Text)
    reversed_meaning: Mapped[str] = mapped_column(Text)
    image_file_id: Mapped[str | None] = mapped_column(Text)
    is_standard: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TarotReading(Base):
    __tablename__ = "tarot_readings"
    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        index=True,
    )
    question: Mapped[str] = mapped_column(Text)
    card_id: Mapped[int] = mapped_column(ForeignKey("tarot_cards.id"))
    orientation: Mapped[str] = mapped_column(String(16))
    prediction: Mapped[str] = mapped_column(Text)
    reading_date: Mapped[str] = mapped_column(String(10), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
