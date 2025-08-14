from aiogram.filters.callback_data import CallbackData


class ProfileCallback(CallbackData, prefix="prof", sep="|"):
    action: str
    page: int = 0
    profile_id: str = ""
