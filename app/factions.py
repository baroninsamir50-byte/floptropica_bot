from __future__ import annotations

WESTERN_FACTION = "ЗАПАДНАЯ ФРАКЦИЯ"
NEUTRAL_DIALOGUE = "НЕЙТРАЛЬНЫЙ ДИАЛОГ"
NO_FACTION = "Не назначена"

FACTIONS = (WESTERN_FACTION, NEUTRAL_DIALOGUE)
TITLES = ("Король", "Королева", "Лидер фракции", "Хорги", "Чародей", "Волшебник", "Жители")

FACTION_DATA: dict[str, dict[str, object]] = {
    WESTERN_FACTION: {
        "icon": "🌅",
        "description": "Сила, выносливость и защита владений.",
        "favored_stats": ("strength", "endurance", "agility"),
        "bonus_text": "При вложении 5 очков в силу, выносливость или ловкость характеристика получает +6.",
    },
    NEUTRAL_DIALOGUE: {
        "icon": "🕊",
        "description": "Интеллект, харизма и магическое влияние.",
        "favored_stats": ("intelligence", "charisma", "magic"),
        "bonus_text": "При вложении 5 очков в интеллект, харизму или магию характеристика получает +6.",
    },
}

VIEW_LABELS = {
    "home": "Главный экран",
    "hero": "Герой",
    "house": "Владения",
    "development": "Развитие",
    "treasury": "Казна",
    "shop": "Магазин дня",
    "inventory": "Снаряжение",
    "map": "Карта",
    "factions": "Фракции",
    "games": "Игровая арена",
    "customization": "Кастомизация",
    "tarot": "Зал Предсказаний",
    "npcs": "NPC",
    "friends": "Друзья",
    "friend-detail": "Просмотр друга",
    "friend-story": "История игрока",
    "statistics": "Статистика",
    "more": "Другие разделы",
}

LEGACY_FACTIONS = {
    "Западная сторона": WESTERN_FACTION,
    "Западная фракция": WESTERN_FACTION,
    "ЗАПАДНАЯ СТОРОНА": WESTERN_FACTION,
    "Нейтральный Диалог": NEUTRAL_DIALOGUE,
    "Нейтральный диалог": NEUTRAL_DIALOGUE,
    "Нет": NO_FACTION,
    "": NO_FACTION,
}

def normalize_faction(value: str | None) -> str:
    if not value:
        return NO_FACTION
    return LEGACY_FACTIONS.get(value.strip(), value.strip())

def faction_development_bonus(faction: str | None, stat: str, spent: int) -> int:
    data = FACTION_DATA.get(normalize_faction(faction))
    if not data or spent != 5:
        return 0
    return 1 if stat in data["favored_stats"] else 0

def faction_payload(faction: str | None) -> dict[str, object]:
    normalized = normalize_faction(faction)
    data = FACTION_DATA.get(normalized)
    if not data:
        return {
            "name": NO_FACTION,
            "icon": "🚩",
            "description": "Фракцию назначает создатель Королевства.",
            "favored_stats": [],
            "bonus_text": "После назначения фракции откроется её бонус развития.",
        }
    return {
        "name": normalized,
        "icon": data["icon"],
        "description": data["description"],
        "favored_stats": list(data["favored_stats"]),
        "bonus_text": data["bonus_text"],
    }
