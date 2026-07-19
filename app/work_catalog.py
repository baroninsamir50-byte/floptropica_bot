from __future__ import annotations

WORK_PROFESSIONS: dict[str, dict[str, object]] = {
    "judge": {
        "name": "Судья",
        "label": "⚖ Судья",
        "gold": (3, 6),
        "xp": (8, 13),
        "bonus_stat": "charisma",
    },
    "magic_alchemist": {
        "name": "Магический Алхимик",
        "label": "🧪 Магический Алхимик",
        "gold": (2, 5),
        "xp": (10, 15),
        "bonus_stat": "magic",
    },
    "refugee_cafe": {
        "name": "Работник волшебной кофейни Беженцев",
        "label": "☕ Волшебная кофейня Беженцев",
        "gold": (3, 7),
        "xp": (6, 11),
        "bonus_stat": "luck",
    },
    "law_creator": {
        "name": "Создатель новых запретов",
        "label": "📜 Создатель новых запретов",
        "gold": (2, 6),
        "xp": (9, 14),
        "bonus_stat": "intelligence",
    },
    "throne_chair": {
        "name": "Председатель на троне Королевы",
        "label": "👑 Председать на троне Королевы",
        "gold": (5, 9),
        "xp": (12, 18),
        "bonus_stat": "charisma",
        "required_titles": {"Король", "Королева"},
    },
    "faction_chair": {
        "name": "Председатель фракции",
        "label": "🚩 Председатель фракции",
        "gold": (4, 8),
        "xp": (10, 16),
        "bonus_stat": "charisma",
        "required_titles": {"Король", "Королева", "Хорги", "Чародей"},
    },
    "royal_designer": {
        "name": "Королевский художник-дизайнер",
        "label": "🎨 Королевский художник-дизайнер",
        "gold": (3, 7),
        "xp": (8, 14),
        "bonus_stat": "charisma",
    },
    "farmer": {
        "name": "Фермер",
        "label": "🌾 Фермер",
        "gold": (3, 8),
        "xp": (6, 12),
        "bonus_stat": "endurance",
    },
    "spirit_exorcist": {
        "name": "Изгоняющий духов",
        "label": "👻 Изгоняющий духов",
        "gold": (4, 8),
        "xp": (11, 17),
        "bonus_stat": "magic",
    },
    "royal_archivist": {
        "name": "Королевский архивариус",
        "label": "📚 Королевский архивариус",
        "gold": (3, 6),
        "xp": (10, 16),
        "bonus_stat": "intelligence",
    },
    "cartographer": {
        "name": "Картограф Королевства",
        "label": "🗺 Картограф Королевства",
        "gold": (3, 7),
        "xp": (9, 15),
        "bonus_stat": "intelligence",
    },
    "anomaly_guard": {
        "name": "Страж аномалий",
        "label": "🌀 Страж аномалий",
        "gold": (4, 8),
        "xp": (11, 17),
        "bonus_stat": "endurance",
    },
    "portal_keeper": {
        "name": "Смотритель порталов",
        "label": "🔮 Смотритель порталов",
        "gold": (4, 7),
        "xp": (12, 18),
        "bonus_stat": "magic",
    },
    "royal_brewer": {
        "name": "Королевский зельевар",
        "label": "⚗ Королевский зельевар",
        "gold": (3, 7),
        "xp": (10, 16),
        "bonus_stat": "luck",
    },
}


def profession_by_key(key: str) -> dict[str, object] | None:
    return WORK_PROFESSIONS.get(key)


def profession_by_name(name: str) -> dict[str, object] | None:
    for data in WORK_PROFESSIONS.values():
        if data["name"] == name:
            return data
    return None


def available_professions(title: str) -> list[tuple[str, dict[str, object]]]:
    result: list[tuple[str, dict[str, object]]] = []
    for key, data in WORK_PROFESSIONS.items():
        required_titles = data.get("required_titles")
        if required_titles and title not in required_titles:
            continue
        result.append((key, data))
    return result


def title_can_use(title: str, data: dict[str, object]) -> bool:
    required_titles = data.get("required_titles")
    return not required_titles or title in required_titles
