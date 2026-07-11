from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👤 Персонаж", callback_data="menu:profile"),
            InlineKeyboardButton(text="🏠 Дом", callback_data="menu:house"),
        ],
        [
            InlineKeyboardButton(text="🏋 Тренировка", callback_data="menu:training"),
            InlineKeyboardButton(text="💼 Работа", callback_data="menu:work"),
        ],
        [
            InlineKeyboardButton(text="🎒 Инвентарь", callback_data="menu:inventory"),
            InlineKeyboardButton(text="🛒 Магазин", callback_data="menu:shop"),
        ],
        [
            InlineKeyboardButton(text="🚩 Фракции", callback_data="menu:factions"),
            InlineKeyboardButton(text="🧑‍🌾 NPC", callback_data="menu:npc"),
        ],
        [InlineKeyboardButton(text="🎲 Игры", callback_data="menu:games")],
    ])


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


def professions_keyboard() -> InlineKeyboardMarkup:
    professions = ["Маг", "Рыцарь", "Алхимик", "Шахтёр", "Кузнец", "Торговец", "Охотник", "Учёный", "Строитель", "Певица"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=p, callback_data=f"profession:{p}")] for p in professions
    ])


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
    roles=[("👤 Гражданин","citizen"),("🌅 Лидер Запада","leader_west"),("🕊 Лидер Диалога","leader_neutral"),("👑 Король","king"),("👑 Королева","queen")]
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
