from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlayerStory
from app.services import get_character
from app.states import StoryCreation

router = Router()

PARTS = (
    ("introduction", "Введение"),
    ("main_part_one", "Основная часть 1"),
    ("main_part_two", "Основная часть 2"),
    ("ending", "Конец"),
)


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✍ Начать по частям", callback_data="story:start")
    ]])


async def require_registered(message: Message, session: AsyncSession):
    character = await get_character(session, message.from_user.id)
    if not character:
        await message.answer("Сначала создайте героя через /start.")
        return None
    return character


@router.message(Command("сюжет", "story", "история"))
async def story_command(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not await require_registered(message, session):
        return
    await state.clear()
    await message.answer(
        "📖 <b>Создание личного сюжета</b>\n\n"
        "Не отправляйте весь рассказ одним сообщением. Бот последовательно запросит четыре части:\n"
        "1. Введение\n2. Основная часть 1\n3. Основная часть 2\n4. Конец\n\n"
        "После каждой части можно прикрепить отдельную фотографию для слайд-шоу. "
        "Текст каждой части — до 4000 символов.",
        reply_markup=start_keyboard(),
    )


@router.callback_query(F.data == "story:start")
async def story_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    character = await get_character(session, callback.from_user.id)
    if not character:
        await callback.answer("Сначала зарегистрируйтесь.", show_alert=True)
        return
    await state.clear()
    await state.set_state(StoryCreation.introduction_text)
    await callback.answer()
    await callback.message.answer("1/4 — отправьте <b>Введение</b> отдельным текстовым сообщением.")


async def save_text(message: Message, state: FSMContext, key: str, next_state, label: str) -> None:
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        await message.answer("Отправьте текст этой части обычным сообщением.")
        return
    if len(text) > 4000:
        await message.answer("Часть длиннее 4000 символов. Сократите её и отправьте снова.")
        return
    await state.update_data(**{key: text})
    await state.set_state(next_state)
    await message.answer(
        f"🖼 Теперь отправьте фотографию для части «{label}» или команду /пропустить."
    )


@router.message(StoryCreation.introduction_text)
async def intro_text(message: Message, state: FSMContext) -> None:
    await save_text(message, state, "introduction", StoryCreation.introduction_photo, "Введение")


@router.message(StoryCreation.main_part_one_text)
async def part_one_text(message: Message, state: FSMContext) -> None:
    await save_text(message, state, "main_part_one", StoryCreation.main_part_one_photo, "Основная часть 1")


@router.message(StoryCreation.main_part_two_text)
async def part_two_text(message: Message, state: FSMContext) -> None:
    await save_text(message, state, "main_part_two", StoryCreation.main_part_two_photo, "Основная часть 2")


@router.message(StoryCreation.ending_text)
async def ending_text(message: Message, state: FSMContext) -> None:
    await save_text(message, state, "ending", StoryCreation.ending_photo, "Конец")


async def advance_after_photo(message: Message, state: FSMContext, image_key: str, next_state, next_prompt: str) -> None:
    if not message.photo:
        await message.answer("Отправьте фотографию или /пропустить.")
        return
    await state.update_data(**{image_key: message.photo[-1].file_id})
    if next_state:
        await state.set_state(next_state)
        await message.answer(next_prompt)
    else:
        await finish_story(message, state)


@router.message(StoryCreation.introduction_photo, F.photo)
async def intro_photo(message: Message, state: FSMContext) -> None:
    await advance_after_photo(message, state, "introduction_image_file_id", StoryCreation.main_part_one_text, "2/4 — отправьте <b>Основную часть 1</b>.")


@router.message(StoryCreation.main_part_one_photo, F.photo)
async def part_one_photo(message: Message, state: FSMContext) -> None:
    await advance_after_photo(message, state, "main_part_one_image_file_id", StoryCreation.main_part_two_text, "3/4 — отправьте <b>Основную часть 2</b>.")


@router.message(StoryCreation.main_part_two_photo, F.photo)
async def part_two_photo(message: Message, state: FSMContext) -> None:
    await advance_after_photo(message, state, "main_part_two_image_file_id", StoryCreation.ending_text, "4/4 — отправьте <b>Конец истории</b>.")


@router.message(StoryCreation.ending_photo, F.photo)
async def ending_photo(message: Message, state: FSMContext) -> None:
    await advance_after_photo(message, state, "ending_image_file_id", None, "")


@router.message(Command("пропустить", "skip"), StoryCreation.introduction_photo)
async def skip_intro_photo(message: Message, state: FSMContext) -> None:
    await state.set_state(StoryCreation.main_part_one_text)
    await message.answer("2/4 — отправьте <b>Основную часть 1</b>.")


@router.message(Command("пропустить", "skip"), StoryCreation.main_part_one_photo)
async def skip_part_one_photo(message: Message, state: FSMContext) -> None:
    await state.set_state(StoryCreation.main_part_two_text)
    await message.answer("3/4 — отправьте <b>Основную часть 2</b>.")


@router.message(Command("пропустить", "skip"), StoryCreation.main_part_two_photo)
async def skip_part_two_photo(message: Message, state: FSMContext) -> None:
    await state.set_state(StoryCreation.ending_text)
    await message.answer("4/4 — отправьте <b>Конец истории</b>.")


@router.message(Command("пропустить", "skip"), StoryCreation.ending_photo)
async def skip_ending_photo(message: Message, state: FSMContext) -> None:
    await finish_story(message, state)


@router.message(Command("сюжет_отмена", "story_cancel"))
async def cancel_story(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Создание сюжета отменено.")


async def finish_story(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    required = ("introduction", "main_part_one", "main_part_two", "ending")
    if any(not data.get(key) for key in required):
        await state.clear()
        await message.answer("Не все части сохранены. Запустите /сюжет заново.")
        return
    # DatabaseMiddleware передаёт сессию только в обработчики, поэтому сохраняем через фабрику.
    from app.database import SessionFactory
    async with SessionFactory() as session:
        character = await get_character(session, message.from_user.id)
        if not character:
            await state.clear()
            await message.answer("Герой не найден.")
            return
        story = await session.scalar(select(PlayerStory).where(PlayerStory.character_id == character.id))
        if not story:
            story = PlayerStory(character_id=character.id, introduction="", main_part_one="", main_part_two="", ending="")
            session.add(story)
        for key in required:
            setattr(story, key, data[key])
        for key in (
            "introduction_image_file_id", "main_part_one_image_file_id",
            "main_part_two_image_file_id", "ending_image_file_id",
        ):
            setattr(story, key, data.get(key))
        story.is_published = True
        await session.commit()
    await state.clear()
    await message.answer(
        "✅ История опубликована. Она появилась в разделе «Друзья» у кнопки «Рассказать историю».\n"
        "Чтобы заменить сюжет, снова используйте /сюжет."
    )
