from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Character, TarotCard, TarotReading
from app.services import local_date
from app.tarot_data import standard_tarot_cards


async def seed_standard_tarot(session: AsyncSession) -> None:
    count = await session.scalar(
        select(func.count(TarotCard.id)).where(TarotCard.is_standard.is_(True))
    )
    if count:
        return

    for card in standard_tarot_cards():
        session.add(TarotCard(
            owner_character_id=None,
            name=str(card["name"]),
            suit=str(card["suit"]),
            number=int(card["number"]),
            description=str(card["description"]),
            upright_meaning=str(card["upright"]),
            reversed_meaning=str(card["reversed"]),
            image_file_id=None,
            is_standard=True,
        ))
    await session.commit()


def prediction_for(
    question: str,
    card: TarotCard,
    orientation: str,
) -> str:
    meaning = (
        card.upright_meaning
        if orientation == "upright"
        else card.reversed_meaning
    )
    normalized = question.lower()

    if any(word in normalized for word in ("люб", "отнош", "чувств", "друж")):
        focus = (
            "В отношениях важнее всего не торопить события и внимательно "
            "смотреть на взаимность поступков."
        )
    elif any(word in normalized for word in ("работ", "золот", "деньг", "казн", "професс")):
        focus = (
            "В вопросах ресурсов карта советует сопоставить желаемую награду "
            "с реальными усилиями и не рисковать всем сразу."
        )
    elif any(word in normalized for word in ("фрак", "регион", "королев", "полит", "выбор")):
        focus = (
            "Для судьбы Королевства значение карты связано с коллективным "
            "решением: одиночная выгода может уступить общему результату."
        )
    elif any(word in normalized for word in ("дом", "защит", "напад", "враг")):
        focus = (
            "В вопросах безопасности лучше заранее укрепить слабое место и "
            "не рассчитывать только на удачу."
        )
    else:
        focus = (
            "Смотрите на карту как на направление для размышления, а не как "
            "на неизбежный итог."
        )

    orientation_label = (
        "прямом положении"
        if orientation == "upright"
        else "перевёрнутом положении"
    )
    return (
        f"Карта «{card.name}» выпала в {orientation_label}. "
        f"{meaning} {focus}"
    )


async def create_daily_reading(
    session: AsyncSession,
    character: Character,
    question: str,
    choice_index: int,
) -> TarotReading:
    today = local_date()
    result = await session.execute(
        select(TarotCard).order_by(TarotCard.id)
    )
    pool = list(result.scalars())
    if not pool:
        raise ValueError("Колода пока пуста.")

    seed_source = f"{character.id}:{today}:{question.strip()}:{datetime.now(timezone.utc).timestamp()}"
    seed = int.from_bytes(
        hashlib.sha256(seed_source.encode("utf-8")).digest()[:8],
        "big",
    )
    rng = random.Random(seed)
    offered = rng.sample(pool, min(3, len(pool)))
    card = offered[choice_index % len(offered)]
    orientation = "upright" if rng.randint(0, 1) == 0 else "reversed"

    reading = TarotReading(
        character_id=character.id,
        question=question.strip(),
        card_id=card.id,
        orientation=orientation,
        prediction=prediction_for(question, card, orientation),
        reading_date=today,
    )
    session.add(reading)
    await session.flush()
    return reading


async def offered_cards(
    session: AsyncSession,
    character: Character,
    question: str,
) -> list[TarotCard]:
    result = await session.execute(select(TarotCard).order_by(TarotCard.id))
    pool = list(result.scalars())
    if not pool:
        return []
    seed_source = f"{character.id}:{local_date()}:{question.strip()}:{datetime.now(timezone.utc).timestamp()}"
    seed = int.from_bytes(
        hashlib.sha256(seed_source.encode("utf-8")).digest()[:8],
        "big",
    )
    rng = random.Random(seed)
    return rng.sample(pool, min(3, len(pool)))
