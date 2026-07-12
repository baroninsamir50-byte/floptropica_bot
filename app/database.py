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
            "ALTER TABLE expeditions ADD COLUMN IF NOT EXISTS party_mana INTEGER NOT NULL DEFAULT 50",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS development_points INTEGER NOT NULL DEFAULT 100",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS work_profession VARCHAR(100)",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS development_pack_date VARCHAR(10)",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS daily_reward_date VARCHAR(10)",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS login_streak INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE house_attacks ADD COLUMN IF NOT EXISTS defender_character_id INTEGER REFERENCES characters(id)",
            "ALTER TABLE house_attacks ADD COLUMN IF NOT EXISTS helped_by_friend BOOLEAN NOT NULL DEFAULT FALSE",
        ]
        for statement in upgrades:
            await connection.execute(text(statement))


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
