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
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS title_reward_date VARCHAR(10)",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS story_reader_achievement_claimed BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS farm_tutorial_completed BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE characters ADD COLUMN IF NOT EXISTS events_tutorial_completed BOOLEAN NOT NULL DEFAULT FALSE",
            "CREATE TABLE IF NOT EXISTS story_reads (id SERIAL PRIMARY KEY, reader_character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE, story_character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE, completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), CONSTRAINT uq_story_reader_author UNIQUE (reader_character_id, story_character_id))",
            "CREATE INDEX IF NOT EXISTS ix_story_reads_reader_character_id ON story_reads(reader_character_id)",
            "CREATE INDEX IF NOT EXISTS ix_story_reads_story_character_id ON story_reads(story_character_id)",
            "ALTER TABLE npc_units ADD COLUMN IF NOT EXISTS upgrade_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE npc_units ADD COLUMN IF NOT EXISTS strength INTEGER NOT NULL DEFAULT 5",
            "ALTER TABLE npc_units ADD COLUMN IF NOT EXISTS endurance INTEGER NOT NULL DEFAULT 5",
            "ALTER TABLE npc_units ADD COLUMN IF NOT EXISTS agility INTEGER NOT NULL DEFAULT 5",
            "ALTER TABLE npc_units ADD COLUMN IF NOT EXISTS skill INTEGER NOT NULL DEFAULT 5",
            "ALTER TABLE npc_units ADD COLUMN IF NOT EXISTS hunger INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE npc_units ADD COLUMN IF NOT EXISTS hunger_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "ALTER TABLE npc_units ADD COLUMN IF NOT EXISTS starvation_started_at TIMESTAMPTZ",
            "ALTER TABLE npc_units ADD COLUMN IF NOT EXISTS exhaustion_started_at TIMESTAMPTZ",
            "CREATE TABLE IF NOT EXISTS farms (id SERIAL PRIMARY KEY, house_id INTEGER NOT NULL UNIQUE REFERENCES houses(id) ON DELETE CASCADE, level INTEGER NOT NULL DEFAULT 1, plot_count INTEGER NOT NULL DEFAULT 3, barn_capacity INTEGER NOT NULL DEFAULT 30, farmer_npc_id INTEGER REFERENCES npc_units(id) ON DELETE SET NULL, auto_feed BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
            "CREATE INDEX IF NOT EXISTS ix_farms_house_id ON farms(house_id)",
            "CREATE INDEX IF NOT EXISTS ix_farms_farmer_npc_id ON farms(farmer_npc_id)",
            "CREATE TABLE IF NOT EXISTS farm_plots (id SERIAL PRIMARY KEY, farm_id INTEGER NOT NULL REFERENCES farms(id) ON DELETE CASCADE, slot INTEGER NOT NULL, crop_slug VARCHAR(40), planted_at TIMESTAMPTZ, water_due_at TIMESTAMPTZ, watered_at TIMESTAMPTZ, ready_at TIMESTAMPTZ, CONSTRAINT uq_farm_plot_slot UNIQUE (farm_id, slot))",
            "CREATE INDEX IF NOT EXISTS ix_farm_plots_farm_id ON farm_plots(farm_id)",
            "CREATE INDEX IF NOT EXISTS ix_farm_plots_crop_slug ON farm_plots(crop_slug)",
            "CREATE TABLE IF NOT EXISTS farm_stock (id SERIAL PRIMARY KEY, farm_id INTEGER NOT NULL REFERENCES farms(id) ON DELETE CASCADE, crop_slug VARCHAR(40) NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, CONSTRAINT uq_farm_crop_stock UNIQUE (farm_id, crop_slug))",
            "CREATE INDEX IF NOT EXISTS ix_farm_stock_farm_id ON farm_stock(farm_id)",
            "CREATE INDEX IF NOT EXISTS ix_farm_stock_crop_slug ON farm_stock(crop_slug)",
            "CREATE TABLE IF NOT EXISTS farm_market_listings (id SERIAL PRIMARY KEY, seller_character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE, crop_slug VARCHAR(40) NOT NULL, quantity INTEGER NOT NULL, unit_price INTEGER NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'active', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), expires_at TIMESTAMPTZ NOT NULL)",
            "CREATE INDEX IF NOT EXISTS ix_farm_market_seller ON farm_market_listings(seller_character_id)",
            "CREATE INDEX IF NOT EXISTS ix_farm_market_crop ON farm_market_listings(crop_slug)",
            "CREATE INDEX IF NOT EXISTS ix_farm_market_status ON farm_market_listings(status)",
            "CREATE TABLE IF NOT EXISTS estate_event_cycles (id SERIAL PRIMARY KEY, character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE, status VARCHAR(20) NOT NULL DEFAULT 'active', chosen_event_ids TEXT NOT NULL DEFAULT '[]', daily_options TEXT NOT NULL DEFAULT '{}', system_event_ids TEXT NOT NULL DEFAULT '[]', result_event_id VARCHAR(40), result_kind VARCHAR(24), result_text TEXT, matched_count INTEGER NOT NULL DEFAULT 0, reward_gold INTEGER NOT NULL DEFAULT 0, reward_item_slug VARCHAR(64), last_choice_date VARCHAR(10), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), resolved_at TIMESTAMPTZ)",
            "CREATE INDEX IF NOT EXISTS ix_estate_event_cycles_character ON estate_event_cycles(character_id)",
            "CREATE INDEX IF NOT EXISTS ix_estate_event_cycles_status ON estate_event_cycles(status)",
            "ALTER TABLE estate_event_cycles ADD COLUMN IF NOT EXISTS result_acknowledged BOOLEAN NOT NULL DEFAULT FALSE",
            "CREATE INDEX IF NOT EXISTS ix_estate_event_cycles_result_acknowledged ON estate_event_cycles(result_acknowledged)",
            "ALTER TABLE estate_event_cycles ADD COLUMN IF NOT EXISTS guard_death_applied BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE characters ALTER COLUMN faction SET DEFAULT 'Не назначена'",
            "ALTER TABLE characters ALTER COLUMN title SET DEFAULT 'Жители'",
            "UPDATE characters SET faction = 'ЗАПАДНАЯ ФРАКЦИЯ' WHERE faction IN ('Западная сторона', 'Западная фракция', 'ЗАПАДНАЯ СТОРОНА')",
            "UPDATE characters SET faction = 'НЕЙТРАЛЬНЫЙ ДИАЛОГ' WHERE faction IN ('Нейтральный Диалог', 'Нейтральный диалог')",
            "UPDATE characters SET faction = 'Не назначена' WHERE faction IS NULL OR faction IN ('Нет', '')",
            "UPDATE characters SET title = 'Жители' WHERE title IN ('Гражданин', 'Обычный житель', 'Житель')",
            "UPDATE characters SET title = 'Лидер фракции' WHERE title LIKE 'Лидер фракции %'",
            "UPDATE characters SET title = 'Волшебник' WHERE title = 'Маг'",
            "UPDATE characters SET title = 'Жители' WHERE title NOT IN ('Король', 'Королева', 'Лидер фракции', 'Хорги', 'Чародей', 'Волшебник', 'Жители')",
        ]
        for statement in upgrades:
            await connection.execute(text(statement))


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
