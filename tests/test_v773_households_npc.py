from app.models import Character, NpcUnit
from app.services import GUARD_UPGRADE_ITEMS, FARMER_UPGRADE_ITEMS, NPC_UPGRADE_ITEMS
from app.miniapp.api import npc_upgrade_requirements


def test_npc_upgrade_sets_are_complete_and_distinct():
    assert len(GUARD_UPGRADE_ITEMS) == 5
    assert len(FARMER_UPGRADE_ITEMS) == 5
    assert set(GUARD_UPGRADE_ITEMS).isdisjoint(FARMER_UPGRADE_ITEMS)
    assert len(NPC_UPGRADE_ITEMS) == 10


def test_upgrade_requirements_match_npc_type():
    assert npc_upgrade_requirements("guard") == GUARD_UPGRADE_ITEMS
    assert npc_upgrade_requirements("peasant") == FARMER_UPGRADE_ITEMS


def test_household_and_festival_columns_exist():
    assert "spouse_character_id" in Character.__table__.columns
    assert "summer_guard_claimed" in Character.__table__.columns
    assert "daily_npc_material_date" in Character.__table__.columns
    assert "upgrade_count" in NpcUnit.__table__.columns
