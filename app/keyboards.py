from app.work_catalog import available_professions
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="👤 Герой", callback_data="menu:profile"),
         InlineKeyboardButton(text="🏰 Владение", callback_data="menu:house")],
        [InlineKeyboardButton(text="🗺 Карта Королевства", callback_data="menu:map")],
        [InlineKeyboardButton(text="🎲 Игровая арена", callback_data="menu:games")],
        [InlineKeyboardButton(text="🏋 Развитие", callback_data="menu:development"),
         InlineKeyboardButton(text="💰 Казна", callback_data="menu:treasury")],
        [InlineKeyboardButton(text="🎒 Снаряжение", callback_data="menu:inventory"),
         InlineKeyboardButton(text="🛒 Магазин дня", callback_data="menu:shop")],
        [InlineKeyboardButton(text="🚩 Фракции", callback_data="menu:factions"),
         InlineKeyboardButton(text="🛡 Защита дома", callback_data="house:defense")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="⚙ Панель создателя", callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def stats_keyboard() -> InlineKeyboardMarkup:
    stats = [
        ("💪 Сила", "strength"), ("🧠 Интеллект", "intelligence"),
        ("🏃 Ловкость", "agility"), ("✨ Магия", "magic"),
        ("🍀 Удача", "luck"), ("🛡 Выносливость", "endurance"),
    ]
    rows = []
    for i in range(0, len(stats), 2):
        rows.append([
            InlineKeyboardButton(text=stats[i][0], callback_data=f"train:{stats[i][1]}"),
            InlineKeyboardButton(text=stats[i+1][0], callback_data=f"train:{stats[i+1][1]}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shop_keyboard(items: list[tuple[int, str, int]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{name} — {price} 🪙", callback_data=f"buy:{item_id}")]
        for item_id, name, price in items
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def inventory_keyboard(items: list[tuple[int, str, bool, str | None]]) -> InlineKeyboardMarkup:
    rows = []
    for inv_id, name, equipped, slot in items:
        if slot:
            label = f"{'✅' if equipped else '⚪'} {name}"
            rows.append([InlineKeyboardButton(text=label, callback_data=f"equip:{inv_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def professions_keyboard(title: str = "") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=str(data["label"]),
            callback_data=f"profession:{key}",
        )]
        for key, data in available_professions(title)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def factions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌅 Западная сторона", callback_data="faction:Западная сторона")],
        [InlineKeyboardButton(text="🕊 Нейтральный Диалог", callback_data="faction:Нейтральный Диалог")],
        [InlineKeyboardButton(text="🚪 Покинуть фракцию", callback_data="faction:Нет")],
    ])


def npc_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Купить крестьянина — 100 🪙", callback_data="npcbuy:peasant")],
        [InlineKeyboardButton(text="Купить стражника — 160 🪙", callback_data="npcbuy:guard")],
        [InlineKeyboardButton(text="Собрать доход крестьян", callback_data="npcincome")],
    ])


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👥 Настройки игроков", callback_data="admin:players")]])

def admin_players_keyboard(players: list[tuple[int,str,str]]) -> InlineKeyboardMarkup:
    rows=[[InlineKeyboardButton(text=f"{name} — {title}", callback_data=f"adminplayer:{tid}")] for tid,name,title in players]
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_roles_keyboard(tid: int) -> InlineKeyboardMarkup:
    roles=[("👤 Гражданин","citizen"),("🌅 Лидер Запада","leader_west"),("🕊 Лидер Диалога","leader_neutral"),("👑 Король","king"),("👑 Королева","queen"),("👸 Королевна","princess")]
    rows=[[InlineKeyboardButton(text=label, callback_data=f"setrole:{tid}:{key}")] for label,key in roles]
    rows.append([InlineKeyboardButton(text="⬅ К игрокам", callback_data="admin:players")])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def games_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔ Как вызвать на дуэль", callback_data="games:duel_help")],
        [InlineKeyboardButton(text="🧭 Создать экспедицию", callback_data="games:expedition_create")],
        [InlineKeyboardButton(text="📜 Правила игр", callback_data="games:rules")],
    ])


def duel_invite_keyboard(duel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"duelaccept:{duel_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"dueldecline:{duel_id}"),
    ]])


def duel_actions_keyboard(duel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚔ Атака", callback_data=f"duelact:{duel_id}:attack"),
            InlineKeyboardButton(text="🔮 Магия", callback_data=f"duelact:{duel_id}:magic"),
        ],
        [
            InlineKeyboardButton(text="🛡 Защита", callback_data=f"duelact:{duel_id}:defend"),
            InlineKeyboardButton(text="🏳 Сдаться", callback_data=f"duelact:{duel_id}:surrender"),
        ],
    ])


def expedition_lobby_keyboard(expedition_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Вступить", callback_data=f"expjoin:{expedition_id}")],
        [InlineKeyboardButton(text="🚀 Начать", callback_data=f"expstart:{expedition_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"expcancel:{expedition_id}")],
    ])


def expedition_choices_keyboard(expedition_id: int, round_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌲 Лесная тропа", callback_data=f"expvote:{expedition_id}:{round_number}:forest")],
        [InlineKeyboardButton(text="🏚 Древние руины", callback_data=f"expvote:{expedition_id}:{round_number}:ruins")],
        [InlineKeyboardButton(text="🌀 Магический портал", callback_data=f"expvote:{expedition_id}:{round_number}:portal")],
    ])



def house_panel_keyboard(active_attack_id: int | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🛡 Состояние защиты", callback_data="house:defense"),
            InlineKeyboardButton(text="🔧 Ремонт", callback_data="house:repair"),
        ],
        [
            InlineKeyboardButton(text="👮 Стража", callback_data="menu:npc"),
            InlineKeyboardButton(text="📜 Последняя угроза", callback_data="house:last_attack"),
        ],
    ]
    if active_attack_id:
        rows.insert(0, [
            InlineKeyboardButton(text="⚔ Защитить лично", callback_data=f"housefight:{active_attack_id}"),
            InlineKeyboardButton(text="👮 Отправить стражу", callback_data=f"houseguards:{active_attack_id}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def house_attack_keyboard(attack_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🏰 Владелец защищает",
                callback_data=f"housefight:{attack_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🤝 Помочь другу",
                callback_data=f"househelp:{attack_id}",
            ),
            InlineKeyboardButton(
                text="👮 Отправить стражу",
                callback_data=f"houseguards:{attack_id}",
            ),
        ],
    ])


def house_battle_keyboard(attack_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚔ Силовая атака", callback_data=f"houseact:{attack_id}:attack"),
            InlineKeyboardButton(text="🔮 Магический удар", callback_data=f"houseact:{attack_id}:magic"),
        ],
        [
            InlineKeyboardButton(text="🛡 Укрепить оборону", callback_data=f"houseact:{attack_id}:defend"),
            InlineKeyboardButton(text="👮 Передать стражникам", callback_data=f"houseguards:{attack_id}"),
        ],
    ])


def repair_house_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔧 Восстановить 10", callback_data="houserepair:10"),
            InlineKeyboardButton(text="🏗 Восстановить максимум", callback_data="houserepair:max"),
        ],
        [InlineKeyboardButton(text="⬅ К дому", callback_data="house:defense")],
    ])


def admin_extended_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Настройки игроков", callback_data="admin:players")],
        [InlineKeyboardButton(text="🖼 Изображения разделов", callback_data="admin:media")],
        [
            InlineKeyboardButton(text="🐉 Напасть на дом", callback_data="admin:attack_players"),
            InlineKeyboardButton(text="🏗 Починить все дома", callback_data="admin:repair_all"),
        ],
        [
            InlineKeyboardButton(text="📢 Событие", callback_data="admin:event_help"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"),
        ],
    ])


def admin_attack_players_keyboard(players: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"🐉 {name}", callback_data=f"adminattack:{telegram_id}")]
        for telegram_id, name in players
    ]
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_media_keyboard() -> InlineKeyboardMarkup:
    media = [
        ("🏛 Фон главной", "home_bg"),
        ("👤 Фон героя", "hero_bg"),
        ("🏰 Фон владения", "house_bg"),
        ("💰 Фон казны", "treasury"),
        ("🛒 Фон магазина", "shop"),
        ("🏋 Фон развития", "development"),
        ("🚩 Фон фракций", "factions"),
        ("🗺 Карта Королевства", "map"),
        ("🎲 Фон игровой арены", "games_bg"),
        ("🎒 Фон инвентаря", "inventory_bg"),
        ("🌌 Фон загрузки", "loading_bg"),
        ("👑 Эмблема приложения", "app_logo"),
        ("🔝 Фон верхней панели", "topbar_bg"),
        ("🔻 Фон нижнего меню", "nav_bg"),
        ("🧱 Текстура карточек", "card_texture"),
        ("🖼 Рамка героя", "frame_hero"),
        ("🏛 Рамка владения", "frame_house"),
        ("👤 Иконка героя", "icon_hero"),
        ("🏰 Иконка дома", "icon_house"),
        ("💰 Иконка казны", "icon_treasury"),
        ("🛒 Иконка магазина", "icon_shop"),
        ("🗺 Иконка карты", "icon_map"),
        ("🎲 Иконка игр", "icon_games"),
        ("🚩 Иконка фракций", "icon_factions"),
        ("🎒 Иконка инвентаря", "icon_inventory"),
        ("🏋 Иконка развития", "icon_development"),
        ("🎁 Иконка подарка", "icon_daily"),
        ("⚔ Фон дуэльной арены", "duel_bg"),
        ("🖼 Рамка бойцов дуэли", "duel_frame"),
        ("VS Знак противостояния", "duel_vs"),
        ("⚙ Иконка кастомизации", "icon_customization"),
    ]
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"adminmedia:{key}")]
        for label, key in media
    ]
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def development_keyboard() -> InlineKeyboardMarkup:
    stats = [
        ("💪 Сила", "strength"), ("🧠 Интеллект", "intelligence"),
        ("🏃 Ловкость", "agility"), ("✨ Магия", "magic"),
        ("🍀 Удача", "luck"), ("🛡 Выносливость", "endurance"),
        ("🎭 Харизма", "charisma"), ("❤️ Здоровье", "health"),
        ("🔮 Мана", "mana"),
    ]
    rows = []
    for label, key in stats:
        rows.append([
            InlineKeyboardButton(text=f"{label} +1", callback_data=f"dev:{key}:1"),
            InlineKeyboardButton(text="+5", callback_data=f"dev:{key}:5"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def treasury_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧰 Выбрать профессию", callback_data="treasury:professions")],
        [InlineKeyboardButton(text="💼 Начать смену", callback_data="treasury:start")],
        [InlineKeyboardButton(text="📦 Получить награду", callback_data="treasury:claim")],
    ])
