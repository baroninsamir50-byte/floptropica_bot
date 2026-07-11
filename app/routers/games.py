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
from app.services import (
    apply_levels, change_gold, get_character, get_effective_stats, percent_bonus,
)

router = Router()


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


async def by_username(session: AsyncSession, username: str) -> Character | None:
    result = await session.execute(
        select(Character).join(User).where(
            func.lower(User.username) == username.lstrip("@").lower()
        )
    )
    return result.scalar_one_or_none()


async def telegram_id_for(session: AsyncSession, character_id: int) -> int | None:
    result = await session.execute(
        select(User.telegram_id).join(Character).where(Character.id == character_id)
    )
    return result.scalar_one_or_none()


async def active_duel(session: AsyncSession, character_id: int) -> Duel | None:
    result = await session.execute(select(Duel).where(
        Duel.status.in_(["invited", "active"]),
        or_(Duel.challenger_id == character_id, Duel.opponent_id == character_id),
    ))
    return result.scalars().first()


async def duel_players(session: AsyncSession, duel: Duel):
    return (
        await session.get(Character, duel.challenger_id),
        await session.get(Character, duel.opponent_id),
    )


async def duel_text(session: AsyncSession, duel: Duel, a: Character, b: Character) -> str:
    sa = await get_effective_stats(session, a)
    sb = await get_effective_stats(session, b)
    turn = a.name if duel.turn_character_id == a.id else b.name
    a_agi = percent_bonus(sa["agility"], sb["agility"])
    b_agi = percent_bonus(sb["agility"], sa["agility"])
    a_end = percent_bonus(sa["endurance"], sb["endurance"])
    b_end = percent_bonus(sb["endurance"], sa["endurance"])
    return (
        f"⚔ <b>Королевская дуэль</b>\n\n"
        f"<b>{a.name}</b>: ❤️ {duel.challenger_hp} | 🔮 {duel.challenger_mana}\n"
        f"Ловкость: +{a_agi}% к уклонению | Выносливость: +{a_end}% к защите\n\n"
        f"<b>{b.name}</b>: ❤️ {duel.opponent_hp} | 🔮 {duel.opponent_mana}\n"
        f"Ловкость: +{b_agi}% к уклонению | Выносливость: +{b_end}% к защите\n\n"
        f"Ход: <b>{turn}</b>"
    )


@router.message(Command("games", "игры"))
async def games(message: Message):
    await message.answer(
        "🎲 <b>Игровая арена Флоптропики</b>\n\n"
        "⚔ <b>Дуэль</b> — характеристики, уровень и экипировка влияют на бой.\n"
        "🧭 <b>Проклятый лабиринт</b> — кооперативное испытание для 2–6 игроков.",
        reply_markup=games_keyboard(),
    )


@router.callback_query(F.data == "menu:games")
async def games_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "🎲 <b>Игровая арена Флоптропики</b>",
        reply_markup=games_keyboard(),
    )


@router.callback_query(F.data == "games:rules")
async def rules(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "⚔ <b>Дуэль</b>\n"
        "Сила — физический урон. Магия и интеллект — заклинания. "
        "Ловкость даёт 1–5% уклонения, выносливость — 1–5% защиты, "
        "удача — 1–5% критического шанса, харизма — шанс собраться при низком здоровье.\n\n"
        "🧭 <b>Лабиринт</b>\n"
        "Лес проверяет силу и ловкость, руины — интеллект и удачу, "
        "портал — магию и запас маны. Выносливость уменьшает урон, "
        "харизма усиливает согласованность команды."
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
        await message.answer("Один из игроков уже занят дуэлью.")
        return

    sc = await get_effective_stats(session, challenger)
    so = await get_effective_stats(session, opponent)
    duel = Duel(
        chat_id=message.chat.id,
        challenger_id=challenger.id,
        opponent_id=opponent.id,
        challenger_hp=sc["health"] + sc["endurance"] * 2 + challenger.level * 2,
        opponent_hp=so["health"] + so["endurance"] * 2 + opponent.level * 2,
        challenger_mana=sc["mana"] + sc["intelligence"],
        opponent_mana=so["mana"] + so["intelligence"],
    )
    session.add(duel)
    await session.flush()
    await message.answer(
        f"⚔ <b>{challenger.name}</b> вызывает <b>{opponent.name}</b> на дуэль!\n"
        "В бою учитываются характеристики и надетые предметы.",
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
    sa = await get_effective_stats(session, a)
    sb = await get_effective_stats(session, b)
    duel.status = "active"
    initiative_a = sa["agility"] + sa["luck"] // 2 + randint(1, 10)
    initiative_b = sb["agility"] + sb["luck"] // 2 + randint(1, 10)
    duel.turn_character_id = a.id if initiative_a >= initiative_b else b.id
    await callback.answer("Дуэль началась!")
    await callback.message.edit_text(
        await duel_text(session, duel, a, b),
        reply_markup=duel_actions_keyboard(duel.id),
    )


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
        "Победитель получает 3 🪙 и 20 XP. Проигравший получает 5 XP."
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
    sa = await get_effective_stats(session, actor)
    st = await get_effective_stats(session, target)
    hp_attr = "opponent_hp" if first else "challenger_hp"
    actor_hp_attr = "challenger_hp" if first else "opponent_hp"
    mana_attr = "challenger_mana" if first else "opponent_mana"
    actor_def = "challenger_defending" if first else "opponent_defending"
    target_def = "opponent_defending" if first else "challenger_defending"

    if action == "surrender":
        await callback.answer()
        await finish_duel(callback, session, duel, target, actor, "соперник сдался")
        return

    log = ""
    if action == "defend":
        setattr(duel, actor_def, True)
        restored = max(1, sa["endurance"] // 4)
        setattr(duel, actor_hp_attr, getattr(duel, actor_hp_attr) + restored)
        log = f"🛡 {actor.name} укрепляет защиту и восстанавливает {restored} здоровья."
    else:
        evade_bonus = percent_bonus(st["agility"], sa["agility"])
        hit_chance = clamp(92 - evade_bonus, 70, 97)
        if randint(1, 100) > hit_chance:
            log = f"💨 {target.name} уклоняется! Ловкость дала +{evade_bonus}% к шансу избежать удара."
        else:
            if action == "magic":
                mana_cost = max(6, 12 - min(5, sa["intelligence"] // 8))
                mana = getattr(duel, mana_attr)
                if mana < mana_cost:
                    await callback.answer(f"Нужно {mana_cost} маны.", show_alert=True)
                    return
                setattr(duel, mana_attr, mana - mana_cost)
                damage = randint(8, 14) + sa["magic"] + sa["intelligence"] // 3
                label = "заклинание"
            else:
                damage = randint(6, 11) + sa["strength"] + actor.level // 2
                crit_bonus = percent_bonus(sa["luck"], st["luck"])
                critical = randint(1, 100) <= 5 + crit_bonus
                if critical:
                    damage = int(damage * 1.55)
                label = "критическую атаку" if critical else "атаку"

            endurance_bonus = percent_bonus(st["endurance"], sa["endurance"])
            damage = max(1, damage - st["endurance"] // 3)
            damage = max(1, int(damage * (100 - endurance_bonus) / 100))
            if getattr(duel, target_def):
                shield = 40 + endurance_bonus
                damage = max(1, int(damage * (100 - shield) / 100))
                setattr(duel, target_def, False)
            setattr(duel, hp_attr, max(0, getattr(duel, hp_attr) - damage))
            log = (
                f"💥 {actor.name} применяет {label}: {damage} урона. "
                f"Выносливость цели снизила урон на {endurance_bonus}%."
            )

    # Харизма даёт 1–5% шанс собраться при критическом здоровье.
    current_hp = getattr(duel, actor_hp_attr)
    max_hp = sa["health"] + sa["endurance"] * 2 + actor.level * 2
    if current_hp > 0 and current_hp <= max_hp // 4:
        resolve = min(5, max(1, sa["charisma"] // 5))
        if randint(1, 100) <= resolve:
            heal = 5 + sa["charisma"] // 4
            setattr(duel, actor_hp_attr, current_hp + heal)
            log += f"\n🎭 Харизма помогает собраться: +{heal} здоровья."

    if getattr(duel, hp_attr) <= 0:
        await callback.answer()
        await finish_duel(callback, session, duel, actor, target, "здоровье соперника закончилось")
        return

    duel.turn_character_id = target.id
    await callback.answer()
    await callback.message.edit_text(
        f"{log}\n\n{await duel_text(session, duel, a, b)}",
        reply_markup=duel_actions_keyboard(duel.id),
    )


# ---------------- EXPEDITION ----------------

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
        "Все характеристики участников складываются в силу команды."
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
        f"❤️ Здоровье отряда: {exp.party_hp}\n"
        f"🔮 Общая мана: {exp.party_mana}\n"
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

    stats = [await get_effective_stats(session, c) for _, c in rows]
    exp.party_hp = 100 + sum(s["health"] + s["endurance"] * 2 for s in stats) // len(stats) // 3
    exp.party_mana = sum(s["mana"] + s["intelligence"] for s in stats) // len(stats)
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
        expedition_id=exp.id, round_number=round_num,
        character_id=char.id, choice=route,
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
    selected = choice([r for r, n in counts.items() if n == top])
    chars = [c for _, c in rows]
    stats = [await get_effective_stats(session, c) for c in chars]

    charisma = sum(s["charisma"] for s in stats)
    endurance = sum(s["endurance"] for s in stats)
    level_power = sum(c.level for c in chars)
    route_names = {
        "forest": "🌲 Лесная тропа",
        "ruins": "🏚 Древние руины",
        "portal": "🌀 Магический портал",
    }

    if selected == "forest":
        core = sum(s["strength"] + s["agility"] for s in stats)
        description = "Команда отбивается от теневых зверей."
    elif selected == "ruins":
        core = sum(s["intelligence"] + s["luck"] for s in stats)
        description = "Команда разгадывает ловушки древних стражей."
    else:
        mana_cost = 8 + len(chars) * 2
        if exp.party_mana >= mana_cost:
            exp.party_mana -= mana_cost
            mana_boost = 12
        else:
            mana_boost = -8
        core = sum(s["magic"] + s["intelligence"] for s in stats) + mana_boost
        description = "Команда стабилизирует опасный магический портал."

    coordination = min(15, charisma // max(1, len(chars) * 4))
    target = len(chars) * 18 + exp.round_number * 4
    chance = clamp(45 + (core + level_power - target) // 3 + coordination, 15, 90)
    passed = randint(1, 100) <= chance

    if passed:
        gain = randint(6, 14) + exp.round_number
        exp.treasure += gain
        outcome = f"✅ Успех с шансом {chance}%. Найдено {gain} золота."
    else:
        base_damage = randint(14, 28) + exp.round_number * 2
        reduction = min(25, endurance // max(1, len(chars) * 3))
        damage = max(5, int(base_damage * (100 - reduction) / 100))
        exp.party_hp = max(0, exp.party_hp - damage)
        outcome = (
            f"❌ Проверка с шансом {chance}% провалена. "
            f"Выносливость уменьшила урон на {reduction}%. Потеряно {damage} здоровья."
        )

    prefix = f"{route_names[selected]}\n{description}\n\n{outcome}"
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
        prefix + f"\n\n{round_text(exp)}",
        reply_markup=expedition_choices_keyboard(exp.id, exp.round_number),
    )
