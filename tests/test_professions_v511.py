from app.work_catalog import (
    available_professions, profession_by_key, profession_income_multiplier,
)

def test_regular_professions_are_open_to_everyone():
    resident = {key for key, _ in available_professions("Жители")}
    assert "faction_chair" in resident
    assert "throne_chair" in resident
    assert "judge" in resident

def test_leader_professions_are_exclusive():
    resident = {key for key, _ in available_professions("Жители")}
    leader = {key for key, _ in available_professions("Лидер фракции")}
    exclusive = {"faction_debates", "faction_development", "senate_chair"}
    assert exclusive.isdisjoint(resident)
    assert exclusive.issubset(leader)

def test_title_income_bonuses():
    judge = profession_by_key("judge")
    debates = profession_by_key("faction_debates")
    assert profession_income_multiplier("Король", judge) == 1.5
    assert profession_income_multiplier("Королева", judge) == 1.5
    assert profession_income_multiplier("Лидер фракции", debates) == 1.2
    assert profession_income_multiplier("Жители", judge) == 1.0

def test_profession_key_exists():
    assert profession_by_key("royal_designer")["name"] == "Королевский художник-дизайнер"
