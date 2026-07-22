from __future__ import annotations

import json
from datetime import datetime, timezone
from random import sample


FARM_PRICE = 70
FARM_START_PLOTS = 3
FARM_BARN_CAPACITY = 30
MARKET_COMMISSION = 0.05

CROPS: dict[str, dict[str, object]] = {
    "sun_wheat": {
        "name": "Солнечная пшеница", "icon": "🌾", "growth_hours": 2,
        "yield": 6, "hunger_restore": 15, "seed_price": 2, "base_price": 3,
        "description": "Быстрая и дешёвая культура для ежедневного питания.",
    },
    "moon_carrot": {
        "name": "Лунная морковь", "icon": "🥕", "growth_hours": 4,
        "yield": 5, "hunger_restore": 25, "seed_price": 4, "base_price": 6,
        "description": "Основной питательный урожай для фермеров и слуг.",
    },
    "mana_mint": {
        "name": "Мана-мята", "icon": "🌿", "growth_hours": 6,
        "yield": 4, "hunger_restore": 20, "seed_price": 6, "base_price": 9,
        "description": "Редкая душистая трава с магическим послевкусием.",
    },
    "fire_pumpkin": {
        "name": "Огненная тыква", "icon": "🎃", "growth_hours": 8,
        "yield": 3, "hunger_restore": 40, "seed_price": 8, "base_price": 14,
        "description": "Сытная культура, особенно полезная для стражи.",
    },
    "royal_grape": {
        "name": "Королевский виноград", "icon": "🍇", "growth_hours": 12,
        "yield": 2, "hunger_restore": 55, "seed_price": 12, "base_price": 22,
        "description": "Редкий урожай с высокой ценой и питательностью.",
    },
}

# Карточки не копируют чужой текст/визуал: это оригинальная игровая база Флоптропики.
ESTATE_EVENTS: list[dict[str, object]] = [
    {"id":"guard_revolt","category":"guard","title":"Стражеское восстание!","icon":"⚔️","description":"Возможно, ваша стража попытается поднять мятеж и захватить замок.","impact":"Владение теряет 40–50% прочности; истощённый стражник может погибнуть."},
    {"id":"captain_plot","category":"guard","title":"Заговор капитана","icon":"🗡️","description":"Капитан караула собирает недовольных у стен владения.","impact":"Лучший стражник временно выбывает, защита ослабевает."},
    {"id":"gate_betrayal","category":"guard","title":"Предательство у ворот","icon":"🚪","description":"Кто-то готов открыть ворота во время следующей атаки.","impact":"Владение получает тяжёлый удар, один стражник ранен."},
    {"id":"guard_desertion","category":"guard","title":"Дезертирство караула","icon":"🏃","description":"Часть охраны готовится покинуть посты перед рассветом.","impact":"Один стражник недоступен 48 часов."},

    {"id":"peasant_theft","category":"farm","title":"Крестьянская кража","icon":"🌾","description":"Фермеры могут попытаться украсть часть урожая из амбара.","impact":"Пропадает до половины запасов урожая."},
    {"id":"harvest_riot","category":"farm","title":"Бунт на жатве","icon":"🔥","description":"Недовольные работники угрожают уничтожить созревшие посевы.","impact":"Готовый урожай на грядках может быть потерян."},
    {"id":"barn_rot","category":"farm","title":"Гниль в амбаре","icon":"🦠","description":"Странная плесень распространяется среди запасов еды.","impact":"Пропадает 30% содержимого амбара."},
    {"id":"seed_swap","category":"farm","title":"Подмена семян","icon":"🫘","description":"Кто-то заменяет ценные семена бесплодными зёрнами.","impact":"До двух грядок становятся пустыми."},

    {"id":"bandit_raid","category":"bandit","title":"Налёт разбойников","icon":"🥷","description":"Шайка разбойников готовит ночной налёт на склады.","impact":"Пропадают до пяти обычных предметов из инвентаря."},
    {"id":"trade_ambush","category":"bandit","title":"Засада на торговом пути","icon":"🛤️","description":"Караван с вашей казной может попасть в засаду.","impact":"Теряется 20–30% монет."},
    {"id":"warehouse_breakin","category":"bandit","title":"Ночной взлом склада","icon":"🔓","description":"Воры изучают замки и распорядок вашей прислуги.","impact":"Пропадают три предмета и часть урожая."},
    {"id":"false_taxmen","category":"bandit","title":"Ложные сборщики налогов","icon":"📜","description":"Самозванцы требуют немедленно отдать королевскую пошлину.","impact":"Теряется 20% монет."},

    {"id":"monster_horde","category":"monster","title":"Набег чудовищ","icon":"👹","description":"Стая чудовищ собирается у границ владения.","impact":"Дом получает 25–35% урона."},
    {"id":"dragon_over_farm","category":"monster","title":"Дракон над фермой","icon":"🐉","description":"Дракон кружит над полями и выбирает место для атаки.","impact":"До двух грядок уничтожаются, ферма страдает."},
    {"id":"rift_rats","category":"monster","title":"Разломные крысы","icon":"🐀","description":"Магические крысы проникли в амбар через трещину пространства.","impact":"Пропадает 40% еды."},
    {"id":"walking_plague","category":"monster","title":"Ходячая чума","icon":"☣️","description":"Заражённое существо приближается к поселению.","impact":"Все NPC получают голод и усталость."},

    {"id":"magic_storm","category":"magic","title":"Магическая буря","icon":"🌩️","description":"Над владением сгущается нестабильная магическая гроза.","impact":"Дом получает 20% урона."},
    {"id":"great_drought","category":"magic","title":"Великая засуха","icon":"☀️","description":"Вода исчезает из колодцев, а земля начинает трескаться.","impact":"Рост культур задерживается."},
    {"id":"cursed_rain","category":"magic","title":"Проклятый дождь","icon":"🌧️","description":"Чёрные капли портят растения и ослабляют урожай.","impact":"Урожай на двух грядках уменьшается."},
    {"id":"forest_wrath","category":"magic","title":"Гнев лесных духов","icon":"🌲","description":"Духи требуют плату за использование древней земли.","impact":"Теряется часть урожая или монет."},
]

for _number, _event in enumerate(ESTATE_EVENTS, start=1):
    _event["number"] = _number
    _event["media_key"] = f"event_card_{_number}"

EVENT_BY_ID = {str(event["id"]): event for event in ESTATE_EVENTS}
CATEGORY_LABELS = {
    "guard": "Стража и перевороты",
    "farm": "Ферма и урожай",
    "bandit": "Разбойники и казна",
    "monster": "Монстры",
    "magic": "Магия и стихии",
}


def json_list(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def json_dict(value: str | None) -> dict[str, list[str]]:
    try:
        parsed = json.loads(value or "{}")
        if not isinstance(parsed, dict):
            return {}
        return {str(key): [str(item) for item in items] for key, items in parsed.items() if isinstance(items, list)}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def event_options(exclude: set[str] | None = None, count: int = 3) -> list[str]:
    pool = [str(event["id"]) for event in ESTATE_EVENTS if str(event["id"]) not in (exclude or set())]
    if len(pool) < count:
        pool = [str(event["id"]) for event in ESTATE_EVENTS]
    return sample(pool, count)


def event_payload(event_id: str) -> dict[str, object]:
    event = EVENT_BY_ID[event_id]
    return {
        **event,
        "category_label": CATEGORY_LABELS[str(event["category"])],
        "image_url": f"/api/miniapp/media/{event['media_key']}",
    }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
