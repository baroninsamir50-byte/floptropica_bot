from app.models import Character, NpcUnit, PlayerStory
from app.services import (
    WORK_SHIFT_LIMIT, NPC_MAX_LEVEL, npc_model_variant,
    npc_upgrade_plan, npc_stat_gains,
)

def test_six_work_shifts():
    assert WORK_SHIFT_LIMIT == 6

def test_npc_upgrade_speed_and_ascensions():
    assert npc_upgrade_plan(1)["cost"] == 3
    assert npc_upgrade_plan(18)["cost"] == 3
    assert npc_upgrade_plan(19)["requires_kit"] is True
    assert npc_upgrade_plan(19)["cost"] == 0
    assert npc_upgrade_plan(20)["cost"] == 8
    assert npc_upgrade_plan(29)["requires_kit"] is True
    assert npc_upgrade_plan(30)["cost"] == 15
    assert npc_upgrade_plan(50)["max_level"] is True
    assert NPC_MAX_LEVEL == 50

def test_npc_appearance_tiers_for_both_types():
    assert npc_model_variant(19) == 1
    assert npc_model_variant(20) == 2
    assert npc_model_variant(29) == 2
    assert npc_model_variant(30) == 3
    assert npc_model_variant(50) == 3

def test_npc_stats_grow_by_role():
    guard = npc_stat_gains("guard")
    farmer = npc_stat_gains("peasant")
    ascended = npc_stat_gains("guard", ascension=True)
    assert guard["strength"] > farmer["strength"]
    assert farmer["skill"] > guard["skill"]
    assert ascended["endurance"] > guard["endurance"]

def test_story_and_title_reward_schema_exists():
    assert "title_reward_date" in Character.__table__.columns
    for column in ("strength", "endurance", "agility", "skill"):
        assert column in NpcUnit.__table__.columns
    for column in ("introduction", "main_part_one", "main_part_two", "ending"):
        assert column in PlayerStory.__table__.columns
