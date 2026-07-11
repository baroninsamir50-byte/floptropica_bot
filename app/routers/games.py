from collections import Counter
from datetime import datetime, timezone
from random import choice, randint

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards import (
    duel_actions_keyboard, duel_invite_keyboard, expedition_choices_keyboard,
    expedition_lobby_keyboard, games_keyboard,
)
from app.models import Character, Duel, Expedition, ExpeditionMember, ExpeditionVote, User
from app.services import apply_levels, change_gold, get_character

router = Router()


async def by_username(session, username):
    result = await session.execute(
        select(Character).join(User).where(func.lower(User.username) == username.lstrip("@").lower())
    )
    return result.scalar_one_or_none()


async def telegram_id_for(session, character_id):
    result = await session.execute(
        select(User.telegram_id).join(Character).where(Character.id == character_id)
    )
    return result.scalar_one_or_none()


async def active_duel(session, character_id):
    result = await session.execute(select(Duel).where(
        Duel.status.in_(["invited", "active"]),
        or_(Duel.challenger_id == character_id, Duel.opponent_id == character_id),
    ))
    return result.scalars().first()


async def duel_players(session, duel):
    return await session.get(Character, duel.challenger_id), await session.get(Character, duel.opponent_id)


def duel_text(duel, a, b):
    turn = a.name if duel.turn_character_id == a.id else b.name
    return (
        f"⚔ <b>Дуэль</b>\n\n"
        f"{a.name}: ❤️ {duel.challenger_hp} | 🔮 {duel.challenger_mana}\n"
        f"{b.name}: ❤️ {duel.opponent_hp} | 🔮 {duel.opponent_mana}\n\n"
        f"Ход: <b>{turn}</b>"
    )


@router.message(Command("games", "игры"))
async def games(message: Message):
    await message.answer(
        "🎲 <b>Игры Королевства</b>\n\n"
        "⚔ Дуэль — бой двух игроков.\n"
        "🧭 Проклятый лабиринт — экспедиция до 6 игроков.",
        reply_markup=games_keyboard(),
    )


@router.callback_query(F.data == "menu:games")
async def games_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("🎲 <b>Игры Королевства</b>", reply_markup=games_keyboard())


@router.callback_query(F.data == "games:rules")
async def rules(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "⚔ Ответьте <code>/duel</code> на сообщение соперника или укажите <code>/duel @username</code>.\n\n"
        "🧭 Введите <code>/expedition</code>. Команда до 6 игроков голосует за путь на пяти этапах."
    )


@router.callback_query(F.data == "games:duel_help")
async def duel_help(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "Ответьте командой <code>/duel</code> на сообщение игрока "
        "или напишите <code>/duel @username</code>."
    )


@router.message(Command("duel", "дуэль"))
async def duel_create(message: Message, session: AsyncSession):
    challenger = await get_character(session, message.from_user.id)
    if not challenger:
        await message.answer("Сначала зарегистрируйтесь в личном чате: /start")
        return

    opponent = None
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.is_bot:
            await message.answer("Нельзя вызвать бота.")
            return
        opponent = await get_character(session, message.reply_to_message.from_user.id)
    else:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) == 2 and parts[1].startswith("@"):
            opponent = await by_username(session, parts[1])

    if not opponent:
        await message.answer("Игрок не найден. Ответьте /duel на сообщение зарегистрированного игрока.")
        return
    if opponent.id == challenger.id:
        await message.answer("Нельзя вызвать самого себя.")
        return
    if await active_duel(session, challenger.id) or await active_duel(session, opponent.id):
        await message.answer("Один из игроков уже участвует в дуэли.")
        return

    duel = Duel(
        chat_id=message.chat.id, challenger_id=challenger.id, opponent_id=opponent.id,
        challenger_hp=max(30, challenger.health), opponent_hp=max(30, opponent.health),
        challenger_mana=challenger.mana, opponent_mana=opponent.mana,
    )
    session.add(duel)
    await session.flush()
    await message.answer(
        f"⚔ <b>{challenger.name}</b> вызывает <b>{opponent.name}</b> на дуэль!",
        reply_markup=duel_invite_keyboard(duel.id),
    )


@router.callback_query(F.data.startswith("duelaccept:"))
async def duel_accept(callback: CallbackQuery, session: AsyncSession):
    duel = await session.get(Duel, int(callback.data.split(":")[1]))
    if not duel or duel.status != "invited":
        await callback.answer("Приглашение недействительно.", show_alert=True)
        return
    if callback.from_user.id != await telegram_id_for(session, duel.opponent_id):
        await callback.answer("Приглашение адресовано другому игроку.", show_alert=True)
        return
    a, b = await duel_players(session, duel)
    duel.status = "active"
    duel.turn_character_id = a.id if a.agility >= b.agility else b.id
    await callback.answer("Дуэль началась!")
    await callback.message.edit_text(duel_text(duel, a, b), reply_markup=duel_actions_keyboard(duel.id))


@router.callback_query(F.data.startswith("dueldecline:"))
async def duel_decline(callback: CallbackQuery, session: AsyncSession):
    duel = await session.get(Duel, int(callback.data.split(":")[1]))
    if not duel or duel.status != "invited":
        await callback.answer("Приглашение недействительно.", show_alert=True)
        return
    if callback.from_user.id != await telegram_id_for(session, duel.opponent_id):
        await callback.answer("Это не ваш вызов.", show_alert=True)
        return
    duel.status = "declined"
    await callback.answer()
    await callback.message.edit_text("❌ Дуэль отклонена.")


async def finish_duel(callback, session, duel, winner, loser, reason):
    duel.status = "finished"
    duel.winner_id = winner.id
    duel.finished_at = datetime.now(timezone.utc)
    await change_gold(session, winner, 3, "duel_win")
    winner.experience += 20
    loser.experience += 5
    apply_levels(winner)
    apply_levels(loser)
    await callback.message.edit_text(
        f"🏆 <b>{winner.name}</b> побеждает!\nПричина: {reason}\n\n"
        "Победитель: 3 🪙 и 20 XP. Проигравший: 5 XP."
    )


@router.callback_query(F.data.startswith("duelact:"))
async def duel_action(callback: CallbackQuery, session: AsyncSession):
    _, duel_id, action = callback.data.split(":", 2)
    duel = await session.get(Duel, int(duel_id))
    if not duel or duel.status != "active":
        await callback.answer("Дуэль завершена.", show_alert=True)
        return
    a, b = await duel_players(session, duel)
    actor = await get_character(session, callback.from_user.id)
    if not actor or actor.id not in {a.id, b.id}:
        await callback.answer("Вы не участвуете.", show_alert=True)
        return
    if duel.turn_character_id != actor.id:
        await callback.answer("Сейчас ход соперника.", show_alert=True)
        return

    first = actor.id == a.id
    target = b if first else a
    hp_attr = "opponent_hp" if first else "challenger_hp"
    mana_attr = "challenger_mana" if first else "opponent_mana"
    actor_def = "challenger_defending" if first else "opponent_defending"
    target_def = "opponent_defending" if first else "challenger_defending"

    if action == "surrender":
        await callback.answer()
        await finish_duel(callback, session, duel, target, actor, "соперник сдался")
        return

    if action == "defend":
        setattr(duel, actor_def, True)
        log = f"🛡 {actor.name} защищается."
    else:
        if action == "magic":
            mana = getattr(duel, mana_attr)
            if mana < 10:
                await callback.answer("Нужно 10 маны.", show_alert=True)
                return
            setattr(duel, mana_attr, mana - 10)
            damage = randint(7, 13) + actor.magic
            label = "заклинание"
        else:
            damage = randint(5, 10) + actor.strength
            critical = randint(1, 100) <= min(35, 5 + actor.luck)
            if critical:
                damage = int(damage * 1.5)
            label = "критический удар" if critical else "атаку"
        damage = max(1, damage - target.endurance // 3)
        if getattr(duel, target_def):
            damage = max(1, damage // 2)
            setattr(duel, target_def, False)
        setattr(duel, hp_attr, max(0, getattr(duel, hp_attr) - damage))
        log = f"💥 {actor.name} применяет {label}: {damage} урона."

    if getattr(duel, hp_attr) <= 0:
        await callback.answer()
        await finish_duel(callback, session, duel, actor, target, "здоровье соперника закончилось")
        return
    duel.turn_character_id = target.id
    await callback.answer()
    await callback.message.edit_text(
        f"{log}\n\n{duel_text(duel, a, b)}",
        reply_markup=duel_actions_keyboard(duel.id),
    )


async def current_exp(session, chat_id):
    result = await session.execute(
        select(Expedition).where(
            Expedition.chat_id == chat_id,
            Expedition.status.in_(["lobby", "active"]),
        ).order_by(Expedition.id.desc())
    )
    return result.scalars().first()


async def members(session, expedition_id):
    result = await session.execute(
        select(ExpeditionMember, Character)
        .join(Character, Character.id == ExpeditionMember.character_id)
        .where(ExpeditionMember.expedition_id == expedition_id)
        .order_by(ExpeditionMember.id)
    )
    return list(result.all())


def lobby_text(exp, rows):
    names = "\n".join(f"• {c.name}" for _, c in rows)
    return (
        "🧭 <b>Экспедиция: Проклятый лабиринт</b>\n\n"
        f"Участники: {len(rows)}/6\n{names}\n\n"
        "Создатель запускает игру после набора команды."
    )


async def create_exp_common(message, user_id, session):
    if message.chat.type == "private":
        await message.answer("Экспедиция создаётся в группе.")
        return
    host = await get_character(session, user_id)
    if not host:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    if await current_exp(session, message.chat.id):
        await message.answer("В этом чате уже есть незавершённая экспедиция.")
        return
    exp = Expedition(chat_id=message.chat.id, host_character_id=host.id)
    session.add(exp)
    await session.flush()
    session.add(ExpeditionMember(expedition_id=exp.id, character_id=host.id, role="Проводник"))
    await session.flush()
    rows = await members(session, exp.id)
    await message.answer(lobby_text(exp, rows), reply_markup=expedition_lobby_keyboard(exp.id))


@router.message(Command("expedition", "экспедиция"))
async def exp_create(message: Message, session: AsyncSession):
    await create_exp_common(message, message.from_user.id, session)


@router.callback_query(F.data == "games:expedition_create")
async def exp_create_cb(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    await create_exp_common(callback.message, callback.from_user.id, session)


@router.callback_query(F.data.startswith("expjoin:"))
async def exp_join(callback: CallbackQuery, session: AsyncSession):
    exp = await session.get(Expedition, int(callback.data.split(":")[1]))
    if not exp or exp.status != "lobby":
        await callback.answer("Набор закрыт.", show_alert=True)
        return
    char = await get_character(session, callback.from_user.id)
    if not char:
        await callback.answer("Сначала зарегистрируйтесь.", show_alert=True)
        return
    rows = await members(session, exp.id)
    if any(c.id == char.id for _, c in rows):
        await callback.answer("Вы уже в команде.", show_alert=True)
        return
    if len(rows) >= 6:
        await callback.answer("Максимум 6 игроков.", show_alert=True)
        return
    session.add(ExpeditionMember(expedition_id=exp.id, character_id=char.id))
    await session.flush()
    rows = await members(session, exp.id)
    await callback.answer("Вы вступили!")
    await callback.message.edit_text(lobby_text(exp, rows), reply_markup=expedition_lobby_keyboard(exp.id))


@router.callback_query(F.data.startswith("expcancel:"))
async def exp_cancel(callback: CallbackQuery, session: AsyncSession):
    exp = await session.get(Expedition, int(callback.data.split(":")[1]))
    host = await get_character(session, callback.from_user.id)
    if not exp or exp.status != "lobby":
        await callback.answer("Недоступно.", show_alert=True)
        return
    if not host or host.id != exp.host_character_id:
        await callback.answer("Только создатель может отменить.", show_alert=True)
        return
    exp.status = "cancelled"
    await callback.answer()
    await callback.message.edit_text("❌ Экспедиция отменена.")


def round_text(exp):
    return (
        f"🧭 <b>Проклятый лабиринт</b>\n\n"
        f"Этап {exp.round_number}/{exp.max_rounds}\n"
        f"❤️ Здоровье отряда: {exp.party_hp}/100\n"
        f"💰 Сокровища: {exp.treasure}\n\n"
        "Каждый участник голосует за путь:"
    )


@router.callback_query(F.data.startswith("expstart:"))
async def exp_start(callback: CallbackQuery, session: AsyncSession):
    exp = await session.get(Expedition, int(callback.data.split(":")[1]))
    host = await get_character(session, callback.from_user.id)
    if not exp or exp.status != "lobby":
        await callback.answer("Уже запущено.", show_alert=True)
        return
    if not host or host.id != exp.host_character_id:
        await callback.answer("Начать может только создатель.", show_alert=True)
        return
    rows = await members(session, exp.id)
    if len(rows) < 2:
        await callback.answer("Нужно минимум 2 игрока, максимум 6.", show_alert=True)
        return
    exp.status = "active"
    exp.round_number = 1
    await callback.answer("Экспедиция началась!")
    await callback.message.edit_text(
        round_text(exp), reply_markup=expedition_choices_keyboard(exp.id, exp.round_number)
    )


async def finish_exp(message, session, exp, success):
    rows = await members(session, exp.id)
    exp.status = "finished"
    exp.finished_at = datetime.now(timezone.utc)
    if success:
        reward = max(1, exp.treasure // len(rows))
        lines = []
        for _, char in rows:
            await change_gold(session, char, reward, "expedition_reward")
            char.experience += 25
            apply_levels(char)
            lines.append(f"• {char.name}: {reward} 🪙 и 25 XP")
        await message.edit_text("🏆 <b>Лабиринт пройден!</b>\n\n" + "\n".join(lines))
    else:
        for _, char in rows:
            char.experience += 5
            apply_levels(char)
        await message.edit_text("💀 Отряд проиграл. Каждый получает 5 XP за попытку.")


@router.callback_query(F.data.startswith("expvote:"))
async def exp_vote(callback: CallbackQuery, session: AsyncSession):
    _, exp_id, round_raw, route = callback.data.split(":", 3)
    exp = await session.get(Expedition, int(exp_id))
    round_num = int(round_raw)
    if not exp or exp.status != "active" or exp.round_number != round_num:
        await callback.answer("Голосование завершено.", show_alert=True)
        return
    char = await get_character(session, callback.from_user.id)
    rows = await members(session, exp.id)
    if not char or char.id not in {c.id for _, c in rows}:
        await callback.answer("Вы не в этой экспедиции.", show_alert=True)
        return
    existing = await session.scalar(select(ExpeditionVote.id).where(
        ExpeditionVote.expedition_id == exp.id,
        ExpeditionVote.round_number == round_num,
        ExpeditionVote.character_id == char.id,
    ))
    if existing:
        await callback.answer("Вы уже проголосовали.", show_alert=True)
        return
    session.add(ExpeditionVote(
        expedition_id=exp.id, round_number=round_num, character_id=char.id, choice=route
    ))
    await session.flush()
    result = await session.execute(select(ExpeditionVote.choice).where(
        ExpeditionVote.expedition_id == exp.id,
        ExpeditionVote.round_number == round_num,
    ))
    votes = list(result.scalars())
    await callback.answer(f"Голос принят: {len(votes)}/{len(rows)}")
    if len(votes) < len(rows):
        return

    counts = Counter(votes)
    top = max(counts.values())
    route = choice([r for r, n in counts.items() if n == top])
    chars = [c for _, c in rows]
    names = {"forest": "🌲 Лесная тропа", "ruins": "🏚 Древние руины", "portal": "🌀 Магический портал"}
    descriptions = {
        "forest": "Отряд встречает теневых волков.",
        "ruins": "Пробуждаются каменные стражи.",
        "portal": "Портал искажает пространство.",
    }
    if route == "forest":
        power = sum(c.strength + c.agility for c in chars)
    elif route == "ruins":
        power = sum(c.intelligence + c.luck for c in chars)
    else:
        power = sum(c.magic + c.endurance for c in chars)
    passed = power + randint(0, len(chars) * 10) >= len(chars) * 12
    if passed:
        gain = randint(5, 12)
        exp.treasure += gain
        outcome = f"✅ Успех! Найдено {gain} золота."
    else:
        damage = randint(10, 24)
        exp.party_hp = max(0, exp.party_hp - damage)
        outcome = f"❌ Отряд теряет {damage} здоровья."

    prefix = f"{names[route]}\n{descriptions[route]}\n\n{outcome}"
    if exp.party_hp <= 0:
        await callback.message.edit_text(prefix)
        await finish_exp(callback.message, session, exp, False)
        return
    if exp.round_number >= exp.max_rounds:
        await callback.message.edit_text(prefix)
        await finish_exp(callback.message, session, exp, True)
        return
    exp.round_number += 1
    await callback.message.edit_text(
        prefix + f"\n\nЭтап {exp.round_number}/{exp.max_rounds}. Выберите путь:",
        reply_markup=expedition_choices_keyboard(exp.id, exp.round_number),
    )
