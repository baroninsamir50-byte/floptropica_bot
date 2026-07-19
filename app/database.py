from collections.abc import AsyncIterator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import get_settings
from app.models import Base

settings = get_settings()
engine = create_async_engine(
    settings.normalized_database_url,
    pool_pre_ping=True,
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def init_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # create_all не добавляет колонки в существующие таблицы,
        # поэтому выполняем безопасные PostgreSQL-обновления.
        upgrades = [
            "ALTER TABLE houses ADD COLUMN IF NOT EXISTS integrity INTEGER NOT NULL DEFAULT 100",
            "ALTER TABLE houses ADD COLUMN IF NOT EXISTS repair_energy INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE houses ADD COLUMN IF NOT EXISTS last_attack_date VARCHAR(10)",
            "ALTER TABLE houses ADD COLUMN IF NOT EXISTS last_cleaning_date VARCHAR(10)",
            "ALTER TABLE houses ADD COLUMN IF NOT EXISTS cleanliness INTEGER NOT NULL DEFAULT 100",
            "ALTER TABLE houses ADD COLUMN IF NOT EXISTS threat_level INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE houses ADD COLUMN IF NOT EXISTS last_cleaning_penalty_date VARCHAR(10)",
            "ALTER TABLE tarot_readings DROP CONSTRAINT IF EXISTS uq_tarot_daily_reading",
            "ALTER TABLE expeditions ADD COLUMN IF NOT EXISTS party_mana INTEGER NOT NULL DEFAULT 50",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS development_points INTEGER NOT NULL DEFAULT 100",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS work_profession VARCHAR(100)",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS development_pack_date VARCHAR(10)",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS daily_reward_date VARCHAR(10)",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS login_streak INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE house_attacks ADD COLUMN IF NOT EXISTS defender_character_id INTEGER REFERENCES characters(id)",
            "ALTER TABLE house_attacks ADD COLUMN IF NOT EXISTS helped_by_friend BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS duel_rating INTEGER NOT NULL DEFAULT 1000",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS duel_wins INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS duel_losses INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS duel_win_streak INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE duels ADD COLUMN IF NOT EXISTS challenger_dodging BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE duels ADD COLUMN IF NOT EXISTS opponent_dodging BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE duels ADD COLUMN IF NOT EXISTS challenger_stamina INTEGER NOT NULL DEFAULT 100",
            "ALTER TABLE duels ADD COLUMN IF NOT EXISTS opponent_stamina INTEGER NOT NULL DEFAULT 100",
            "ALTER TABLE duels ADD COLUMN IF NOT EXISTS challenger_style VARCHAR(24) NOT NULL DEFAULT 'guardian'",
            "ALTER TABLE duels ADD COLUMN IF NOT EXISTS opponent_style VARCHAR(24) NOT NULL DEFAULT 'guardian'",
            "ALTER TABLE duels ADD COLUMN IF NOT EXISTS challenger_potion_used BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE duels ADD COLUMN IF NOT EXISTS opponent_potion_used BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE duels ADD COLUMN IF NOT EXISTS round_number INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE duels ADD COLUMN IF NOT EXISTS battle_log TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS current_view VARCHAR(40) NOT NULL DEFAULT 'Вне Mini App'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS spouse_character_id INTEGER REFERENCES characters(id)",
            "CREATE INDEX IF NOT EXISTS ix_characters_spouse_character_id ON characters(spouse_character_id)",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS summer_guard_claimed BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS daily_npc_material_date VARCHAR(10)",
            "ALTER TABLE npc_units ADD COLUMN IF NOT EXISTS upgrade_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE characters ALTER COLUMN faction SET DEFAULT 'Не назначена'",
            "ALTER TABLE characters ALTER COLUMN title SET DEFAULT 'Жители'",
            "UPDATE characters SET faction = 'ЗАПАДНАЯ ФРАКЦИЯ' WHERE faction IN ('Западная сторона', 'Западная фракция', 'ЗАПАДНАЯ СТОРОНА')",
            "UPDATE characters SET faction = 'НЕЙТРАЛЬНЫЙ ДИАЛОГ' WHERE faction IN ('Нейтральный Диалог', 'Нейтральный диалог')",
            "UPDATE characters SET faction = 'Не назначена' WHERE faction IS NULL OR faction IN ('Нет', '')",
            "UPDATE characters SET title = 'Жители' WHERE title IN ('Гражданин', 'Обычный житель', 'Житель')",
            "UPDATE characters SET title = 'Жители' WHERE title LIKE 'Лидер фракции %'",
            "UPDATE characters SET title = 'Жители' WHERE title NOT IN ('Король', 'Королева', 'Хорги', 'Чародей', 'Жители')",
        ]
        for statement in upgrades:
            await connection.execute(text(statement))


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
