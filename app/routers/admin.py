from datetime import datetime, timedelta, timezone
from random import choice

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.keyboards import (
    admin_attack_players_keyboard,
    admin_extended_keyboard,
    admin_event_media_keyboard,
    admin_media_keyboard,
    admin_marriage_keyboard,
    admin_players_keyboard,
    admin_roles_keyboard,
    house_attack_keyboard,
)
from app.models import Character, GameEvent, House, HouseAttack, User
from app.factions import WESTERN_FACTION, NEUTRAL_DIALOGUE, NO_FACTION, VIEW_LABELS
from app.farm_events import ESTATE_EVENTS
from app.services import (
    apply_levels,
    change_gold,
    get_character,
    set_system_media,
)
from app.states import AdminMediaUpload

router = Router()

TITLE_DATA = {
    "king": "Король",
    "queen": "Королева",
    "faction_leader": "Лидер фракции",
    "horgi": "Хорги",
    "sorcerer": "Чародей",
    "wizard": "Волшебник",
    "residents": "Жители",
}

FACTION_ASSIGNMENTS = {
    "west": WESTERN_FACTION,
    "neutral": NEUTRAL_DIALOGUE,
    "none": NO_FACTION,
}

MEDIA_NAMES = {
    "home_bg": "фона главной страницы",
    "hero_bg": "фона раздела героя",
    "house_bg": "фона раздела владения",
    "treasury": "фона казны",
    "shop": "фона магазина дня",
    "development": "фона развития",
    "factions": "фона фракций",
    "map": "карты Королевства",
    "games_bg": "фона игровой арены",
    "inventory_bg": "фона инвентаря",
    "loading_bg": "фона загрузочного экрана",
    "app_logo": "эмблемы Mini App",
    "topbar_bg": "фона верхней панели",
    "nav_bg": "фона нижней навигации",
    "card_texture": "текстуры игровых карточек",
    "frame_hero": "декоративной рамки героя",
    "frame_house": "декоративной рамки владения",
    "icon_hero": "иконки героя",
    "icon_house": "иконки дома",
    "icon_treasury": "иконки казны",
    "icon_shop": "иконки магазина",
    "icon_map": "иконки карты",
    "icon_games": "иконки игр",
    "icon_factions": "иконки фракций",
    "icon_inventory": "иконки инвентаря",
    "icon_development": "иконки развития",
    "icon_daily": "иконки ежедневного подарка",
    "duel_bg": "фона дуэльной арены",
    "duel_frame": "рамки бойцов дуэли",
    "duel_vs": "знака VS",
    "icon_customization": "иконки кастомизации",
    "tarot_bg": "фона Зала Предсказаний",
    "tarot_back": "рубашки карт Таро",
    "icon_tarot": "иконки раздела Таро",
    "npc_bg": "фона раздела NPC",
    "farm_bg": "фона фермы",
    "icon_farm": "иконки фермы",
    "icon_npc": "иконки NPC",
    "room_bg": "фона комнат",
    "enemy_dragon_1": "модели дракона 1",
    "enemy_dragon_2": "модели дракона 2",
    "enemy_dragon_3": "модели дракона 3",
    "enemy_monster_1": "модели монстра 1",
    "enemy_monster_2": "модели монстра 2",
    "enemy_monster_3": "модели монстра 3",
    "enemy_anomaly_1": "модели аномалии 1",
    "enemy_anomaly_2": "модели аномалии 2",
    "enemy_anomaly_3": "модели аномалии 3",
    "guard_model_1": "модели стражника 1",
    "guard_model_2": "модели стражника 2",
    "guard_model_3": "модели стражника 3",
    "peasant_model_1": "модели крестьянина 1",
    "peasant_model_2": "модели крестьянина 2",
    "peasant_model_3": "модели крестьянина 3",
    "npc_peasant_1": "облика NPC: Крестьянин — облик 1",
    "npc_peasant_2": "облика NPC: Крестьянин — облик 2",
    "npc_peasant_3": "облика NPC: Крестьянин — облик 3",
    "npc_farmer_1": "облика NPC: Фермер — облик 1",
    "npc_farmer_2": "облика NPC: Фермер — облик 2",
    "npc_farmer_3": "облика NPC: Фермер — облик 3",
    "npc_gardener_1": "облика NPC: Садовник — облик 1",
    "npc_gardener_2": "облика NPC: Садовник — облик 2",
    "npc_gardener_3": "облика NPC: Садовник — облик 3",
    "npc_forester_1": "облика NPC: Лесник — облик 1",
    "npc_forester_2": "облика NPC: Лесник — облик 2",
    "npc_forester_3": "облика NPC: Лесник — облик 3",
    "npc_miner_1": "облика NPC: Шахтёр — облик 1",
    "npc_miner_2": "облика NPC: Шахтёр — облик 2",
    "npc_miner_3": "облика NPC: Шахтёр — облик 3",
    "npc_fisher_1": "облика NPC: Рыбак — облик 1",
    "npc_fisher_2": "облика NPC: Рыбак — облик 2",
    "npc_fisher_3": "облика NPC: Рыбак — облик 3",
    "npc_cook_1": "облика NPC: Повар — облик 1",
    "npc_cook_2": "облика NPC: Повар — облик 2",
    "npc_cook_3": "облика NPC: Повар — облик 3",
    "npc_recruit_1": "облика NPC: Новобранец — облик 1",
    "npc_recruit_2": "облика NPC: Новобранец — облик 2",
    "npc_recruit_3": "облика NPC: Новобранец — облик 3",
    "npc_guard_1": "облика NPC: Стражник — облик 1",
    "npc_guard_2": "облика NPC: Стражник — облик 2",
    "npc_guard_3": "облика NPC: Стражник — облик 3",
    "npc_veteran_1": "облика NPC: Ветеран — облик 1",
    "npc_veteran_2": "облика NPC: Ветеран — облик 2",
    "npc_veteran_3": "облика NPC: Ветеран — облик 3",
    "npc_archer_1": "облика NPC: Лучник — облик 1",
    "npc_archer_2": "облика NPC: Лучник — облик 2",
    "npc_archer_3": "облика NPC: Лучник — облик 3",
    "npc_rider_1": "облика NPC: Всадник — облик 1",
    "npc_rider_2": "облика NPC: Всадник — облик 2",
    "npc_rider_3": "облика NPC: Всадник — облик 3",
    "npc_paladin_1": "облика NPC: Паладин — облик 1",
    "npc_paladin_2": "облика NPC: Паладин — облик 2",
    "npc_paladin_3": "облика NPC: Паладин — облик 3",
    "npc_dragon_tamer_1": "облика NPC: Укротитель драконов — облик 1",
    "npc_dragon_tamer_2": "облика NPC: Укротитель драконов — облик 2",
    "npc_dragon_tamer_3": "облика NPC: Укротитель драконов — облик 3",
    "npc_mage_1": "облика NPC: Маг — облик 1",
    "npc_mage_2": "облика NPC: Маг — облик 2",
    "npc_mage_3": "облика NPC: Маг — облик 3",
    "npc_seer_1": "облика NPC: Провидец — облик 1",
    "npc_seer_2": "облика NPC: Провидец — облик 2",
    "npc_seer_3": "облика NPC: Провидец — облик 3",
    "npc_alchemist_1": "облика NPC: Алхимик — облик 1",
    "npc_alchemist_2": "облика NPC: Алхимик — облик 2",
    "npc_alchemist_3": "облика NPC: Алхимик — облик 3",
    "npc_exorcist_1": "облика NPC: Экзорцист — облик 1",
    "npc_exorcist_2": "облика NPC: Экзорцист — облик 2",
    "npc_exorcist_3": "облика NPC: Экзорцист — облик 3",
    "npc_archmage_1": "облика NPC: Архимаг — облик 1",
    "npc_archmage_2": "облика NPC: Архимаг — облик 2",
    "npc_archmage_3": "облика NPC: Архимаг — облик 3",
    "npc_merchant_1": "облика NPC: Торговец — облик 1",
    "npc_merchant_2": "облика NPC: Торговец — облик 2",
    "npc_merchant_3": "облика NPC: Торговец — облик 3",
    "npc_banker_1": "облика NPC: Банкир — облик 1",
    "npc_banker_2": "облика NPC: Банкир — облик 2",
    "npc_banker_3": "облика NPC: Банкир — облик 3",
    "npc_quartermaster_1": "облика NPC: Интендант — облик 1",
    "npc_quartermaster_2": "облика NPC: Интендант — облик 2",
    "npc_quartermaster_3": "облика NPC: Интендант — облик 3",
    "npc_treasurer_1": "облика NPC: Казначей — облик 1",
    "npc_treasurer_2": "облика NPC: Казначей — облик 2",
    "npc_treasurer_3": "облика NPC: Казначей — облик 3",
    "npc_judge_1": "облика NPC: Судья — облик 1",
    "npc_judge_2": "облика NPC: Судья — облик 2",
    "npc_judge_3": "облика NPC: Судья — облик 3",
    "npc_scribe_1": "облика NPC: Писарь — облик 1",
    "npc_scribe_2": "облика NPC: Писарь — облик 2",
    "npc_scribe_3": "облика NPC: Писарь — облик 3",
    "npc_advisor_1": "облика NPC: Советник — облик 1",
    "npc_advisor_2": "облика NPC: Советник — облик 2",
    "npc_advisor_3": "облика NPC: Советник — облик 3",
    "npc_chancellor_1": "облика NPC: Канцлер — облик 1",
    "npc_chancellor_2": "облика NPC: Канцлер — облик 2",
    "npc_chancellor_3": "облика NPC: Канцлер — облик 3",
    "npc_bard_1": "облика NPC: Бард — облик 1",
    "npc_bard_2": "облика NPC: Бард — облик 2",
    "npc_bard_3": "облика NPC: Бард — облик 3",
    "npc_artist_1": "облика NPC: Художник — облик 1",
    "npc_artist_2": "облика NPC: Художник — облик 2",
    "npc_artist_3": "облика NPC: Художник — облик 3",
    "npc_librarian_1": "облика NPC: Библиотекарь — облик 1",
    "npc_librarian_2": "облика NPC: Библиотекарь — облик 2",
    "npc_librarian_3": "облика NPC: Библиотекарь — облик 3",
    "npc_architect_1": "облика NPC: Архитектор — облик 1",
    "npc_architect_2": "облика NPC: Архитектор — облик 2",
    "npc_architect_3": "облика NPC: Архитектор — облик 3",
    "npc_dog_1": "облика NPC: Пёс — облик 1",
    "npc_dog_2": "облика NPC: Пёс — облик 2",
    "npc_dog_3": "облика NPC: Пёс — облик 3",
    "npc_cat_1": "облика NPC: Кот — облик 1",
    "npc_cat_2": "облика NPC: Кот — облик 2",
    "npc_cat_3": "облика NPC: Кот — облик 3",
    "npc_falcon_1": "облика NPC: Сокол — облик 1",
    "npc_falcon_2": "облика NPC: Сокол — облик 2",
    "npc_falcon_3": "облика NPC: Сокол — облик 3",
    "npc_small_dragon_1": "облика NPC: Маленький дракон — облик 1",
    "npc_small_dragon_2": "облика NPC: Маленький дракон — облик 2",
    "npc_small_dragon_3": "облика NPC: Маленький дракон — облик 3",
    "npc_royal_architect_1": "облика NPC: Королевский архитектор — облик 1",
    "npc_royal_architect_2": "облика NPC: Королевский архитектор — облик 2",
    "npc_royal_architect_3": "облика NPC: Королевский архитектор — облик 3",
    "npc_great_magister_1": "облика NPC: Великий магистр — облик 1",
    "npc_great_magister_2": "облика NPC: Великий магистр — облик 2",
    "npc_great_magister_3": "облика NPC: Великий магистр — облик 3",
    "npc_royal_general_1": "облика NPC: Генерал Королевства — облик 1",
    "npc_royal_general_2": "облика NPC: Генерал Королевства — облик 2",
    "npc_royal_general_3": "облика NPC: Генерал Королевства — облик 3",
    "npc_forest_keeper_1": "облика NPC: Хранитель леса — облик 1",
    "npc_forest_keeper_2": "облика NPC: Хранитель леса — облик 2",
    "npc_forest_keeper_3": "облика NPC: Хранитель леса — облик 3",
    "npc_angel_of_light_1": "облика NPC: Ангел света — облик 1",
    "npc_angel_of_light_2": "облика NPC: Ангел света — облик 2",
    "npc_angel_of_light_3": "облика NPC: Ангел света — облик 3",
}


def is_admin(user_id: int) -> bool:
    return user_id in get_settings().admins


async def deny_callback(callback: CallbackQuery) -> bool:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return True
    return False


async def show_admin_home(message: Message) -> None:
    await message.answer(
        "⚙ <b>Панель создателя</b>\n\n"
        "Управление игроками, изображениями, домами и событиями.",
        reply_markup=admin_extended_keyboard(),
    )


MEDIA_NAMES.update({f"event_card_{event['number']}": f"карточки события №{event['number']} — {event['title']}" for event in ESTATE_EVENTS})


@router.message(Command("admin"))
async def admin_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(
            "Недостаточно прав.\n"
            f"Ваш Telegram ID: <code>{message.from_user.id}</code>\n"
            "Добавьте его в переменную ADMIN_IDS на Render."
        )
        return
    await show_admin_home(message)


@router.callback_query(F.data == "admin:home")
async def admin_home(callback: CallbackQuery) -> None:
    if await deny_callback(callback):
        return
    await callback.answer()
    await callback.message.edit_text(
        "⚙ <b>Панель создателя</b>",
        reply_markup=admin_extended_keyboard(),
    )


@router.callback_query(F.data == "admin:players")
async def admin_players(callback: CallbackQuery, session: AsyncSession) -> None:
    if await deny_callback(callback):
        return
    result = await session.execute(
        select(User.telegram_id, Character.name, Character.title, User.current_view)
        .join(Character, Character.user_id == User.id)
        .order_by(Character.name)
    )
    players = list(result.all())
    await callback.answer()
    if not players:
        await callback.message.edit_text(
            "Зарегистрированных игроков пока нет.",
            reply_markup=admin_extended_keyboard(),
        )
        return
    await callback.message.edit_text(
        "👥 <b>Выберите игрока</b>",
        reply_markup=admin_players_keyboard(players),
    )


@router.callback_query(F.data.startswith("adminplayer:"))
async def admin_player(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if await deny_callback(callback):
        return
    telegram_id = int(callback.data.split(":", 1)[1])
    character = await get_character(session, telegram_id)
    if not character:
        await callback.answer("Игрок не найден.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        f"👤 <b>{character.name}</b>\n"
        f"Telegram ID: <code>{telegram_id}</code>\n"
        f"Титул: {character.title}\n"
        f"Фракция: {character.faction}\n"
        f"Статус: {character.social_status}\n"
        f"Сейчас в игре: {VIEW_LABELS.get(character.user.current_view, character.user.current_view or 'Вне Mini App')}\n"
        f"Последняя активность: {character.user.last_seen_at.strftime('%d.%m %H:%M') if character.user.last_seen_at else 'не зафиксирована'}\n\n"
        "Назначьте титул или фракцию:",
        reply_markup=admin_roles_keyboard(telegram_id),
    )


@router.callback_query(F.data.startswith("settitle:"))
async def set_title(callback: CallbackQuery, session: AsyncSession) -> None:
    if await deny_callback(callback):
        return
    _, telegram_id_raw, title_key = callback.data.split(":", 2)
    title = TITLE_DATA.get(title_key)
    if not title:
        await callback.answer("Неизвестный титул.", show_alert=True)
        return
    character = await get_character(session, int(telegram_id_raw))
    if not character:
        await callback.answer("Игрок не найден.", show_alert=True)
        return
    character.title = title
    await callback.answer("Титул назначен.", show_alert=True)
    await callback.message.edit_text(
        f"✅ <b>{character.name}</b>\nТитул: <b>{character.title}</b>\nФракция: {character.faction}",
        reply_markup=admin_roles_keyboard(int(telegram_id_raw)),
    )


@router.callback_query(F.data.startswith("setfaction:"))
async def set_faction(callback: CallbackQuery, session: AsyncSession) -> None:
    if await deny_callback(callback):
        return
    _, telegram_id_raw, faction_key = callback.data.split(":", 2)
    faction = FACTION_ASSIGNMENTS.get(faction_key)
    if not faction:
        await callback.answer("Неизвестная фракция.", show_alert=True)
        return
    character = await get_character(session, int(telegram_id_raw))
    if not character:
        await callback.answer("Игрок не найден.", show_alert=True)
        return
    character.faction = faction
    await callback.answer("Фракция назначена.", show_alert=True)
    await callback.message.edit_text(
        f"✅ <b>{character.name}</b>\nТитул: {character.title}\nФракция: <b>{character.faction}</b>",
        reply_markup=admin_roles_keyboard(int(telegram_id_raw)),
    )


@router.callback_query(F.data.startswith("marriagepick:"))
async def marriage_pick(callback: CallbackQuery, session: AsyncSession) -> None:
    if await deny_callback(callback):
        return
    target_tid = int(callback.data.split(":", 1)[1])
    result = await session.execute(
        select(User.telegram_id, Character.name)
        .join(Character, Character.user_id == User.id)
        .order_by(Character.name)
    )
    await callback.answer()
    await callback.message.edit_text(
        "💍 <b>Выберите второго игрока</b>\n\nПосле назначения бюджет, комнаты и NPC станут общими.",
        reply_markup=admin_marriage_keyboard(target_tid, list(result.all())),
    )


@router.callback_query(F.data.startswith("setmarriage:"))
async def set_marriage(callback: CallbackQuery, session: AsyncSession) -> None:
    if await deny_callback(callback):
        return
    _, first_tid_raw, second_tid_raw = callback.data.split(":", 2)
    first = await get_character(session, int(first_tid_raw))
    second = await get_character(session, int(second_tid_raw))
    if not first or not second:
        await callback.answer("Игрок не найден.", show_alert=True)
        return
    if first.id == second.id:
        await callback.answer("Нельзя назначить брак с самим собой.", show_alert=True)
        return
    if first.spouse_character_id and first.spouse_character_id != second.id:
        await callback.answer("Первый игрок уже состоит в браке.", show_alert=True)
        return
    if second.spouse_character_id and second.spouse_character_id != first.id:
        await callback.answer("Второй игрок уже состоит в браке.", show_alert=True)
        return
    shared_gold = first.gold + second.gold if first.spouse_character_id != second.id else max(first.gold, second.gold)
    first.gold = second.gold = shared_gold
    first.spouse_character_id = second.id
    second.spouse_character_id = first.id
    first.social_status = second.social_status = "В браке"
    await callback.answer("Совместный дом создан.", show_alert=True)
    await callback.message.edit_text(
        f"💍 <b>{first.name}</b> и <b>{second.name}</b> теперь в браке.\nОбщий бюджет: {shared_gold} 🪙",
        reply_markup=admin_roles_keyboard(int(first_tid_raw)),
    )


@router.callback_query(F.data.startswith("clearmarriage:"))
async def clear_marriage_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    if await deny_callback(callback):
        return
    telegram_id = int(callback.data.split(":", 1)[1])
    character = await get_character(session, telegram_id)
    if not character:
        await callback.answer("Игрок не найден.", show_alert=True)
        return
    spouse = await session.get(Character, character.spouse_character_id) if character.spouse_character_id else None
    if spouse and spouse.spouse_character_id == character.id:
        balance = max(character.gold, spouse.gold)
        character.gold = balance // 2 + balance % 2
        spouse.gold = balance // 2
        spouse.spouse_character_id = None
        spouse.social_status = "Не в браке"
    character.spouse_character_id = None
    character.social_status = "Не в браке"
    await callback.answer("Статус брака снят.", show_alert=True)
    await callback.message.edit_text(
        f"💔 <b>{character.name}</b> больше не состоит в браке.",
        reply_markup=admin_roles_keyboard(telegram_id),
    )


@router.callback_query(F.data == "admin:event_media")
async def admin_event_media_panel(callback: CallbackQuery) -> None:
    if await deny_callback(callback):
        return
    await callback.answer()
    event_rows = "\n\n".join(
        f"{event['number']}. <b>{event['title']}</b>\n{event['impact']}"
        for event in ESTATE_EVENTS
    )
    await callback.message.edit_text(
        "🎴 <b>Оформление событий владения</b>\n\n"
        f"{event_rows}\n\n"
        "Выберите номер события и отправьте вертикальную картинку 4:5.",
        reply_markup=admin_event_media_keyboard(ESTATE_EVENTS),
    )


@router.callback_query(F.data.startswith("adminevent:"))
async def admin_event_media_request(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if await deny_callback(callback):
        return
    try:
        number = int(callback.data.split(":", 1)[1])
    except (TypeError, ValueError):
        await callback.answer("Неизвестный номер.", show_alert=True)
        return
    event = next((item for item in ESTATE_EVENTS if int(item["number"]) == number), None)
    if not event:
        await callback.answer("Событие не найдено.", show_alert=True)
        return
    key = f"event_card_{number}"
    await state.set_state(AdminMediaUpload.photo)
    await state.update_data(media_key=key)
    await callback.answer()
    await callback.message.answer(
        f"🎴 <b>Событие №{number}: {event['title']}</b>\n\n"
        f"{event['description']}\n\n"
        f"<b>Последствие:</b> {event['impact']}\n\n"
        "Отправьте изображение карточки. Рекомендуемый формат: 1080×1350 (4:5)."
    )


@router.callback_query(F.data == "admin:media")
async def admin_media_panel(callback: CallbackQuery) -> None:
    if await deny_callback(callback):
        return
    await callback.answer()
    await callback.message.edit_text(
        "🖼 <b>Изображения разделов</b>\n\n"
        "Выберите раздел, затем отправьте одну фотографию.",
        reply_markup=admin_media_keyboard(),
    )


@router.callback_query(F.data.startswith("adminmedia:"))
async def admin_media_request(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if await deny_callback(callback):
        return
    key = callback.data.split(":", 1)[1]
    if key not in MEDIA_NAMES:
        await callback.answer("Неизвестный раздел.", show_alert=True)
        return
    await state.set_state(AdminMediaUpload.photo)
    await state.update_data(media_key=key)
    await callback.answer()
    await callback.message.answer(
        f"📸 Отправьте новую фотографию для раздела "
        f"<b>{MEDIA_NAMES[key]}</b>."
    )


@router.message(AdminMediaUpload.photo, F.photo)
async def admin_media_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    key = data.get("media_key")
    if key not in MEDIA_NAMES:
        await state.clear()
        await message.answer("Не удалось определить раздел.")
        return

    await set_system_media(session, key, message.photo[-1].file_id)
    await state.clear()
    event_card = str(key).startswith("event_card_")
    await message.answer(
        f"✅ Фотография раздела <b>{MEDIA_NAMES[key]}</b> обновлена."
        + ("\nВыберите следующее событие для оформления." if event_card else ""),
        reply_markup=(admin_event_media_keyboard(ESTATE_EVENTS) if event_card else admin_media_keyboard()),
    )


@router.message(AdminMediaUpload.photo)
async def admin_media_invalid(message: Message) -> None:
    await message.answer("Нужно отправить фотографию как изображение.")


@router.callback_query(F.data == "admin:attack_players")
async def admin_attack_players(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if await deny_callback(callback):
        return
    result = await session.execute(
        select(User.telegram_id, Character.name)
        .join(Character, Character.user_id == User.id)
        .order_by(Character.name)
    )
    players = list(result.all())
    await callback.answer()
    if not players:
        await callback.message.edit_text(
            "Зарегистрированных игроков пока нет.",
            reply_markup=admin_extended_keyboard(),
        )
        return
    await callback.message.edit_text(
        "🐉 <b>Выберите дом для тестового нападения</b>",
        reply_markup=admin_attack_players_keyboard(players),
    )


@router.callback_query(F.data.startswith("adminattack:"))
async def admin_force_attack(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if await deny_callback(callback):
        return

    telegram_id = int(callback.data.split(":", 1)[1])
    character = await get_character(session, telegram_id)
    if not character or not character.house:
        await callback.answer("Дом игрока не найден.", show_alert=True)
        return

    result = await session.execute(
        select(HouseAttack).where(
            HouseAttack.house_id == character.house.id,
            HouseAttack.status.in_(
                ["waiting", "player_fighting", "guards_fighting"]
            ),
        )
    )
    if result.scalars().first():
        await callback.answer(
            "На этот дом уже идёт нападение.",
            show_alert=True,
        )
        return

    enemy_name, enemy_type, base_power = choice([
        ("🐉 Дракон", "dragon", 44),
        ("👹 Болотный урод", "monster", 32),
        ("🌀 Аномалия", "anomaly", 40),
    ])
    attack = HouseAttack(
        house_id=character.house.id,
        enemy_name=enemy_name,
        enemy_type=enemy_type,
        enemy_power=base_power + character.level * 2,
        enemy_hp=60 + base_power + character.level * 2,
        response_deadline=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    session.add(attack)
    await session.flush()

    settings = get_settings()
    if settings.game_chat_id:
        try:
            await callback.bot.send_message(
                settings.game_chat_id,
                f"⚠ <b>ТЕСТОВОЕ НАПАДЕНИЕ!</b>\n"
                f"{enemy_name} атакует владение <b>{character.house.name}</b>.\n"
                f"Владелец: {character.name}",
                reply_markup=house_attack_keyboard(attack.id),
            )
        except Exception:
            pass

    await callback.answer("Нападение создано.", show_alert=True)


@router.callback_query(F.data == "admin:repair_all")
async def admin_repair_all(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if await deny_callback(callback):
        return
    result = await session.execute(select(House))
    houses = list(result.scalars())
    for house in houses:
        house.integrity = 100
    await callback.answer(
        f"Восстановлено домов: {len(houses)}",
        show_alert=True,
    )


@router.callback_query(F.data == "admin:stats")
async def admin_stats(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if await deny_callback(callback):
        return

    players_count = await session.scalar(
        select(func.count(Character.id))
    ) or 0
    houses_count = await session.scalar(
        select(func.count(House.id))
    ) or 0
    active_attacks = await session.scalar(
        select(func.count(HouseAttack.id)).where(
            HouseAttack.status.in_(
                ["waiting", "player_fighting", "guards_fighting"]
            )
        )
    ) or 0

    await callback.answer()
    await callback.message.edit_text(
        f"📊 <b>Статистика Королевства</b>\n\n"
        f"Игроков: {players_count}\n"
        f"Домов: {houses_count}\n"
        f"Активных нападений: {active_attacks}",
        reply_markup=admin_extended_keyboard(),
    )


@router.callback_query(F.data == "admin:event_help")
async def admin_event_help(callback: CallbackQuery) -> None:
    if await deny_callback(callback):
        return
    await callback.answer()
    await callback.message.edit_text(
        "Для запуска события используйте:\n"
        "<code>/запустить_событие Текст события</code>",
        reply_markup=admin_extended_keyboard(),
    )


async def find_character(
    session: AsyncSession,
    telegram_id: int,
) -> Character | None:
    result = await session.execute(
        select(Character)
        .join(User)
        .where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


@router.message(Command("дать_золото"))
async def give_gold(
    message: Message,
    session: AsyncSession,
) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Формат: /дать_золото TELEGRAM_ID AMOUNT")
        return

    try:
        telegram_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("ID и сумма должны быть числами.")
        return

    character = await find_character(session, telegram_id)
    if not character:
        await message.answer("Игрок не найден.")
        return

    try:
        await change_gold(
            session,
            character,
            amount,
            f"admin:{message.from_user.id}",
        )
        await message.answer(f"Готово. Баланс игрока: {character.gold}")
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command("дать_опыт"))
async def give_xp(
    message: Message,
    session: AsyncSession,
) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Формат: /дать_опыт TELEGRAM_ID AMOUNT")
        return

    try:
        telegram_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("ID и опыт должны быть числами.")
        return

    character = await find_character(session, telegram_id)
    if not character:
        await message.answer("Игрок не найден.")
        return

    character.experience += max(0, amount)
    levels = apply_levels(character)
    await message.answer(
        f"Готово. Уровень: {character.level}. "
        f"Повышений: {levels}."
    )


@router.message(Command("запустить_событие"))
async def launch_event(
    message: Message,
    session: AsyncSession,
) -> None:
    if not is_admin(message.from_user.id):
        return

    title = (message.text or "").partition(" ")[2].strip()
    if not title:
        await message.answer("Формат: /запустить_событие ТЕКСТ")
        return

    session.add(GameEvent(title=title))
    await message.answer(f"⚠ Событие запущено:\n\n{title}")
