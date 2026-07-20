from app.work_catalog import available_professions
from app.factions import WESTERN_FACTION, NEUTRAL_DIALOGUE, NO_FACTION, VIEW_LABELS
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
        [InlineKeyboardButton(text="ℹ Фракцию назначает создатель", callback_data="faction:locked")],
    ])


def npc_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Купить крестьянина — 100 🪙", callback_data="npcbuy:peasant")],
        [InlineKeyboardButton(text="Купить стражника — 160 🪙", callback_data="npcbuy:guard")],
        [InlineKeyboardButton(text="Собрать доход крестьян", callback_data="npcincome")],
    ])


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👥 Настройки игроков", callback_data="admin:players")]])

def admin_players_keyboard(players: list[tuple[int, str, str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"{name} — {title} · {VIEW_LABELS.get(view, view or 'Вне Mini App')}",
        callback_data=f"adminplayer:{tid}",
    )] for tid, name, title, view in players]
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_roles_keyboard(tid: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="👑 Король", callback_data=f"settitle:{tid}:king"),
         InlineKeyboardButton(text="👑 Королева", callback_data=f"settitle:{tid}:queen")],
        [InlineKeyboardButton(text="🚩 Лидер фракции", callback_data=f"settitle:{tid}:faction_leader")],
        [InlineKeyboardButton(text="✨ Хорги", callback_data=f"settitle:{tid}:horgi"),
         InlineKeyboardButton(text="🔮 Чародей", callback_data=f"settitle:{tid}:sorcerer")],
        [InlineKeyboardButton(text="🪄 Волшебник", callback_data=f"settitle:{tid}:wizard"),
         InlineKeyboardButton(text="👥 Жители", callback_data=f"settitle:{tid}:residents")],
        [InlineKeyboardButton(text=f"🌅 {WESTERN_FACTION}", callback_data=f"setfaction:{tid}:west")],
        [InlineKeyboardButton(text=f"🕊 {NEUTRAL_DIALOGUE}", callback_data=f"setfaction:{tid}:neutral")],
        [InlineKeyboardButton(text="🚩 Без фракции", callback_data=f"setfaction:{tid}:none")],
        [InlineKeyboardButton(text="💍 Назначить брак", callback_data=f"marriagepick:{tid}"),
         InlineKeyboardButton(text="💔 Снять брак", callback_data=f"clearmarriage:{tid}")],
        [InlineKeyboardButton(text="⬅ К игрокам", callback_data="admin:players")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)



def admin_marriage_keyboard(target_tid: int, players: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"💍 {name}", callback_data=f"setmarriage:{target_tid}:{telegram_id}",
    )] for telegram_id, name in players if telegram_id != target_tid]
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"adminplayer:{target_tid}")])
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
        ("🔮 Фон Зала Предсказаний", "tarot_bg"),
        ("🂠 Рубашка карт Таро", "tarot_back"),
        ("🔮 Иконка Таро", "icon_tarot"),
        ("👥 Фон NPC", "npc_bg"),
        ("👥 Иконка NPC", "icon_npc"),
        ("🚪 Фон комнат", "room_bg"),
        ("🐉 Дракон 1", "enemy_dragon_1"),
        ("🐉 Дракон 2", "enemy_dragon_2"),
        ("🐉 Дракон 3", "enemy_dragon_3"),
        ("👹 Монстр 1", "enemy_monster_1"),
        ("👹 Монстр 2", "enemy_monster_2"),
        ("👹 Монстр 3", "enemy_monster_3"),
        ("🌀 Аномалия 1", "enemy_anomaly_1"),
        ("🌀 Аномалия 2", "enemy_anomaly_2"),
        ("🌀 Аномалия 3", "enemy_anomaly_3"),
        ("🛡 Стражник 1", "guard_model_1"),
        ("🛡 Стражник 2", "guard_model_2"),
        ("🛡 Стражник 3", "guard_model_3"),
        ("🌾 Крестьянин 1", "peasant_model_1"),
        ("🌾 Крестьянин 2", "peasant_model_2"),
        ("🌾 Крестьянин 3", "peasant_model_3"),
        ("⚔ Фон дуэльной арены", "duel_bg"),
        ("🖼 Рамка бойцов дуэли", "duel_frame"),
        ("VS Знак противостояния", "duel_vs"),
        ("⚙ Иконка кастомизации", "icon_customization"),
        ("👥 Крестьянин — облик 1", "npc_peasant_1"),
        ("👥 Крестьянин — облик 2", "npc_peasant_2"),
        ("👥 Крестьянин — облик 3", "npc_peasant_3"),
        ("👥 Фермер — облик 1", "npc_farmer_1"),
        ("👥 Фермер — облик 2", "npc_farmer_2"),
        ("👥 Фермер — облик 3", "npc_farmer_3"),
        ("👥 Садовник — облик 1", "npc_gardener_1"),
        ("👥 Садовник — облик 2", "npc_gardener_2"),
        ("👥 Садовник — облик 3", "npc_gardener_3"),
        ("👥 Лесник — облик 1", "npc_forester_1"),
        ("👥 Лесник — облик 2", "npc_forester_2"),
        ("👥 Лесник — облик 3", "npc_forester_3"),
        ("👥 Шахтёр — облик 1", "npc_miner_1"),
        ("👥 Шахтёр — облик 2", "npc_miner_2"),
        ("👥 Шахтёр — облик 3", "npc_miner_3"),
        ("👥 Рыбак — облик 1", "npc_fisher_1"),
        ("👥 Рыбак — облик 2", "npc_fisher_2"),
        ("👥 Рыбак — облик 3", "npc_fisher_3"),
        ("👥 Повар — облик 1", "npc_cook_1"),
        ("👥 Повар — облик 2", "npc_cook_2"),
        ("👥 Повар — облик 3", "npc_cook_3"),
        ("👥 Новобранец — облик 1", "npc_recruit_1"),
        ("👥 Новобранец — облик 2", "npc_recruit_2"),
        ("👥 Новобранец — облик 3", "npc_recruit_3"),
        ("👥 Стражник — облик 1", "npc_guard_1"),
        ("👥 Стражник — облик 2", "npc_guard_2"),
        ("👥 Стражник — облик 3", "npc_guard_3"),
        ("👥 Ветеран — облик 1", "npc_veteran_1"),
        ("👥 Ветеран — облик 2", "npc_veteran_2"),
        ("👥 Ветеран — облик 3", "npc_veteran_3"),
        ("👥 Лучник — облик 1", "npc_archer_1"),
        ("👥 Лучник — облик 2", "npc_archer_2"),
        ("👥 Лучник — облик 3", "npc_archer_3"),
        ("👥 Всадник — облик 1", "npc_rider_1"),
        ("👥 Всадник — облик 2", "npc_rider_2"),
        ("👥 Всадник — облик 3", "npc_rider_3"),
        ("👥 Паладин — облик 1", "npc_paladin_1"),
        ("👥 Паладин — облик 2", "npc_paladin_2"),
        ("👥 Паладин — облик 3", "npc_paladin_3"),
        ("👥 Укротитель драконов — облик 1", "npc_dragon_tamer_1"),
        ("👥 Укротитель драконов — облик 2", "npc_dragon_tamer_2"),
        ("👥 Укротитель драконов — облик 3", "npc_dragon_tamer_3"),
        ("👥 Маг — облик 1", "npc_mage_1"),
        ("👥 Маг — облик 2", "npc_mage_2"),
        ("👥 Маг — облик 3", "npc_mage_3"),
        ("👥 Провидец — облик 1", "npc_seer_1"),
        ("👥 Провидец — облик 2", "npc_seer_2"),
        ("👥 Провидец — облик 3", "npc_seer_3"),
        ("👥 Алхимик — облик 1", "npc_alchemist_1"),
        ("👥 Алхимик — облик 2", "npc_alchemist_2"),
        ("👥 Алхимик — облик 3", "npc_alchemist_3"),
        ("👥 Экзорцист — облик 1", "npc_exorcist_1"),
        ("👥 Экзорцист — облик 2", "npc_exorcist_2"),
        ("👥 Экзорцист — облик 3", "npc_exorcist_3"),
        ("👥 Архимаг — облик 1", "npc_archmage_1"),
        ("👥 Архимаг — облик 2", "npc_archmage_2"),
        ("👥 Архимаг — облик 3", "npc_archmage_3"),
        ("👥 Торговец — облик 1", "npc_merchant_1"),
        ("👥 Торговец — облик 2", "npc_merchant_2"),
        ("👥 Торговец — облик 3", "npc_merchant_3"),
        ("👥 Банкир — облик 1", "npc_banker_1"),
        ("👥 Банкир — облик 2", "npc_banker_2"),
        ("👥 Банкир — облик 3", "npc_banker_3"),
        ("👥 Интендант — облик 1", "npc_quartermaster_1"),
        ("👥 Интендант — облик 2", "npc_quartermaster_2"),
        ("👥 Интендант — облик 3", "npc_quartermaster_3"),
        ("👥 Казначей — облик 1", "npc_treasurer_1"),
        ("👥 Казначей — облик 2", "npc_treasurer_2"),
        ("👥 Казначей — облик 3", "npc_treasurer_3"),
        ("👥 Судья — облик 1", "npc_judge_1"),
        ("👥 Судья — облик 2", "npc_judge_2"),
        ("👥 Судья — облик 3", "npc_judge_3"),
        ("👥 Писарь — облик 1", "npc_scribe_1"),
        ("👥 Писарь — облик 2", "npc_scribe_2"),
        ("👥 Писарь — облик 3", "npc_scribe_3"),
        ("👥 Советник — облик 1", "npc_advisor_1"),
        ("👥 Советник — облик 2", "npc_advisor_2"),
        ("👥 Советник — облик 3", "npc_advisor_3"),
        ("👥 Канцлер — облик 1", "npc_chancellor_1"),
        ("👥 Канцлер — облик 2", "npc_chancellor_2"),
        ("👥 Канцлер — облик 3", "npc_chancellor_3"),
        ("👥 Бард — облик 1", "npc_bard_1"),
        ("👥 Бард — облик 2", "npc_bard_2"),
        ("👥 Бард — облик 3", "npc_bard_3"),
        ("👥 Художник — облик 1", "npc_artist_1"),
        ("👥 Художник — облик 2", "npc_artist_2"),
        ("👥 Художник — облик 3", "npc_artist_3"),
        ("👥 Библиотекарь — облик 1", "npc_librarian_1"),
        ("👥 Библиотекарь — облик 2", "npc_librarian_2"),
        ("👥 Библиотекарь — облик 3", "npc_librarian_3"),
        ("👥 Архитектор — облик 1", "npc_architect_1"),
        ("👥 Архитектор — облик 2", "npc_architect_2"),
        ("👥 Архитектор — облик 3", "npc_architect_3"),
        ("👥 Пёс — облик 1", "npc_dog_1"),
        ("👥 Пёс — облик 2", "npc_dog_2"),
        ("👥 Пёс — облик 3", "npc_dog_3"),
        ("👥 Кот — облик 1", "npc_cat_1"),
        ("👥 Кот — облик 2", "npc_cat_2"),
        ("👥 Кот — облик 3", "npc_cat_3"),
        ("👥 Сокол — облик 1", "npc_falcon_1"),
        ("👥 Сокол — облик 2", "npc_falcon_2"),
        ("👥 Сокол — облик 3", "npc_falcon_3"),
        ("👥 Маленький дракон — облик 1", "npc_small_dragon_1"),
        ("👥 Маленький дракон — облик 2", "npc_small_dragon_2"),
        ("👥 Маленький дракон — облик 3", "npc_small_dragon_3"),
        ("👥 Королевский архитектор — облик 1", "npc_royal_architect_1"),
        ("👥 Королевский архитектор — облик 2", "npc_royal_architect_2"),
        ("👥 Королевский архитектор — облик 3", "npc_royal_architect_3"),
        ("👥 Великий магистр — облик 1", "npc_great_magister_1"),
        ("👥 Великий магистр — облик 2", "npc_great_magister_2"),
        ("👥 Великий магистр — облик 3", "npc_great_magister_3"),
        ("👥 Генерал Королевства — облик 1", "npc_royal_general_1"),
        ("👥 Генерал Королевства — облик 2", "npc_royal_general_2"),
        ("👥 Генерал Королевства — облик 3", "npc_royal_general_3"),
        ("👥 Хранитель леса — облик 1", "npc_forest_keeper_1"),
        ("👥 Хранитель леса — облик 2", "npc_forest_keeper_2"),
        ("👥 Хранитель леса — облик 3", "npc_forest_keeper_3"),
        ("👥 Ангел света — облик 1", "npc_angel_of_light_1"),
        ("👥 Ангел света — облик 2", "npc_angel_of_light_2"),
        ("👥 Ангел света — облик 3", "npc_angel_of_light_3"),
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
