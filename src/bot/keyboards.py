from math import ceil

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.api.xui_api import XUIApi
from src.bot.callbacks import ProfileCallback
from src.core.config import settings

PROFILES_PER_PAGE = 10


async def get_profiles_markup(page: int = 0) -> tuple[str, InlineKeyboardMarkup | None]:
    api = XUIApi(settings.PANEL_URL, settings.PANEL_LOGIN, settings.PANEL_PASSWORD)
    api.login()
    profiles = api.get_profiles(settings.VLESS_INBOUND_ID)

    if not profiles:
        return "📭 Список профилей пуст.", None

    total_pages = ceil(len(profiles) / PROFILES_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start_index = page * PROFILES_PER_PAGE
    end_index = start_index + PROFILES_PER_PAGE
    paginated_profiles = profiles[start_index:end_index]

    text = f"📄 <b>Список профилей (Страница {page + 1}/{total_pages}):</b>\n\n"
    keyboard = []
    for i, profile in enumerate(paginated_profiles, start=start_index + 1):
        text += (
            f"{i}. <code>{profile['remark']}</code> (-> {profile['outbound_tag']})\n"
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"🗑️ Удалить {profile['remark']}",
                    callback_data=ProfileCallback(
                        action="confirm_delete",
                        page=page,
                        profile_id=profile["profile_id"],
                    ).pack(),
                )
            ]
        )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=ProfileCallback(action="list", page=page - 1).pack(),
            )
        )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=ProfileCallback(action="list", page=page + 1).pack(),
            )
        )
    if nav_buttons:
        keyboard.append(nav_buttons)

    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)
