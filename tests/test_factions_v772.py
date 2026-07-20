from app.factions import (
    WESTERN_FACTION, NEUTRAL_DIALOGUE, TITLES,
    faction_development_bonus, normalize_faction,
)

def test_exact_factions():
    assert normalize_faction("Западная сторона") == WESTERN_FACTION
    assert normalize_faction("Нейтральный Диалог") == NEUTRAL_DIALOGUE

def test_exact_titles():
    assert TITLES == (
        "Король", "Королева", "Лидер фракции", "Хорги",
        "Чародей", "Волшебник", "Жители",
    )

def test_faction_development_bonus():
    assert faction_development_bonus(WESTERN_FACTION, "strength", 5) == 1
    assert faction_development_bonus(WESTERN_FACTION, "magic", 5) == 0
    assert faction_development_bonus(NEUTRAL_DIALOGUE, "charisma", 5) == 1
    assert faction_development_bonus(NEUTRAL_DIALOGUE, "charisma", 1) == 0
