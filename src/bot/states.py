from aiogram.fsm.state import State, StatesGroup


class ProfileCreation(StatesGroup):
    waiting_for_proxy_details = State()
