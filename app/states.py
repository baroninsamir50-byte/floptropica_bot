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
