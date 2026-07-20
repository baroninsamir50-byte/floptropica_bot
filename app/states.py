from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    name = State()
    portrait = State()
    house_name = State()
    house_photo = State()


class ChangePortrait(StatesGroup):
    photo = State()


class ChangeHousePhoto(StatesGroup):
    photo = State()


class AdminMediaUpload(StatesGroup):
    photo = State()


class StoryCreation(StatesGroup):
    introduction_text = State()
    introduction_photo = State()
    main_part_one_text = State()
    main_part_one_photo = State()
    main_part_two_text = State()
    main_part_two_photo = State()
    ending_text = State()
    ending_photo = State()
