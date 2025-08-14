import asyncio
import logging
import re

from aiogram import F, Router
from aiogram.filters import (
    Command,
    CommandObject,
    CommandStart,
    StateFilter,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import any_state
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.markdown import hcode

from src.api.xui_api import XUIApi
from src.bot.callbacks import ProfileCallback
from src.bot.keyboards import get_profiles_markup
from src.bot.states import ProfileCreation
from src.core.config import settings

router = Router()


def parse_args_with_limits(args: list[str]) -> dict:
    remark_parts = []
    limit = 0
    days = 0
    for part in args:
        if match := re.match(r"limit=(\d+)", part, re.IGNORECASE):
            limit = int(match.group(1))
        elif match := re.match(r"days=(\d+)", part, re.IGNORECASE):
            days = int(match.group(1))
        else:
            remark_parts.append(part)
    return {"remark": " ".join(remark_parts), "limit": limit, "days": days}


async def create_proxy_profile(
    message: Message,
    host: str,
    port: str,
    user: str,
    password: str,
    remark: str,
    limit: int,
    days: int,
):
    api = XUIApi(settings.PANEL_URL, settings.PANEL_LOGIN, settings.PANEL_PASSWORD)
    api.login()

    sanitized_remark = remark.lower().replace(" ", "-").replace(":", "-")
    if api.is_profile_exists(sanitized_remark, settings.VLESS_INBOUND_ID):
        await message.answer(f"❌ <b>Профиль с именем '{remark}' уже существует.</b>")
        return

    msg = await message.answer("Имя свободно. Начинаю работу... ⏳")
    try:
        await msg.edit_text("Шаг 1/5: Получение данных инбаунда...")
        inbound_info = api.get_inbound(settings.VLESS_INBOUND_ID)

        outbound_tag = f"out-{sanitized_remark[:20]}"
        await msg.edit_text(f"Шаг 2/5: Добавление аутбаунда (тег: {outbound_tag})...")
        api.add_outbound(outbound_tag, host, port, user, password)

        client_remark = f"user-{sanitized_remark[:20]}"
        await msg.edit_text(
            f"Шаг 3/5: Создание клиента (примечание: {client_remark})..."
        )
        new_uuid = api.add_client_to_inbound(
            settings.VLESS_INBOUND_ID, client_remark, total_gb=limit, expiry_days=days
        )

        await msg.edit_text("Шаг 4/5: Создание правила маршрутизации...")
        api.add_routing_rule(client_remark, outbound_tag, settings.VLESS_INBOUND_ID)

        await msg.edit_text("Шаг 5/5: Перезапуск Xray и генерация ссылки...")
        api.restart_xray()
        await asyncio.sleep(3)

        vless_uri = api.get_vless_uri(
            settings.VLESS_INBOUND_ID, new_uuid, remark, inbound_data=inbound_info
        )

        await msg.delete()
        await message.answer(
            f"✅ <b>Готово! Профиль '{remark}' создан.</b>\n\n"
            f"Лимиты: {limit or '∞'} ГБ, {days or '∞'} дней.\n\n"
            "Ссылка для подключения (нажмите, чтобы скопировать):\n"
            f"{hcode(vless_uri)}"
        )
    except Exception as e:
        logging.error(f"Ошибка при создании прокси-профиля: {e}", exc_info=True)
        await msg.edit_text(f"❌ <b>Что-то пошло не так.</b>\n\n<b>Ошибка:</b> {e}")


async def create_direct_vless_profile(
    message: Message, remark: str, limit: int, days: int
):
    api = XUIApi(settings.PANEL_URL, settings.PANEL_LOGIN, settings.PANEL_PASSWORD)
    api.login()

    sanitized_remark = remark.lower().replace(" ", "-").replace(":", "-")
    if api.is_profile_exists(sanitized_remark, settings.VLESS_INBOUND_ID):
        await message.answer(f"❌ <b>Профиль с именем '{remark}' уже существует.</b>")
        return

    msg = await message.answer("Имя свободно. Начинаю работу... ⏳")
    try:
        await msg.edit_text("Шаг 1/4: Получение данных инбаунда...")
        inbound_info = api.get_inbound(settings.VLESS_INBOUND_ID)

        client_remark = f"user-{sanitized_remark[:20]}"
        await msg.edit_text(
            f"Шаг 2/4: Создание клиента (примечание: {client_remark})..."
        )
        new_uuid = api.add_client_to_inbound(
            settings.VLESS_INBOUND_ID,
            client_remark,
            total_gb=limit,
            expiry_days=days,
            flow="xtls-rprx-vision-udp443",
        )

        await msg.edit_text("Шаг 3/4: Создание правила маршрутизации (на 'direct')...")
        api.add_routing_rule(client_remark, "direct", settings.VLESS_INBOUND_ID)

        await msg.edit_text("Шаг 4/4: Перезапуск Xray и генерация ссылки...")
        api.restart_xray()
        await asyncio.sleep(3)

        vless_uri = api.get_vless_uri(
            settings.VLESS_INBOUND_ID, new_uuid, remark, inbound_data=inbound_info
        )

        await msg.delete()
        await message.answer(
            f"✅ <b>Готово! 'Чистый' VLESS профиль '{remark}' создан.</b>\n\n"
            f"Лимиты: {limit or '∞'} ГБ, {days or '∞'} дней.\n\n"
            "Ссылка для подключения (нажмите, чтобы скопировать):\n"
            f"{hcode(vless_uri)}"
        )
    except Exception as e:
        logging.error(f"Ошибка при создании VLESS-профиля: {e}", exc_info=True)
        await msg.edit_text(f"❌ <b>Что-то пошло не так.</b>\n\n<b>Ошибка:</b> {e}")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Я бот для управления прокси-профилями.\n\n"
        "▪️ /new <code>host:port:user:pass Название [limit=ГБ] [days=ДНЕЙ]</code> - создать профиль через прокси\n"
        "▪️ /vless <code>Название [limit=ГБ] [days=ДНЕЙ]</code> - создать 'чистый' VLESS профиль\n"
        "▪️ /list - показать все профили\n"
        "▪️ /cancel - отменить текущее действие"
    )


@router.message(Command("cancel"), StateFilter(any_state))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активных действий для отмены.")
        return

    logging.info("Cancelling state %r", current_state)
    await state.clear()
    await message.answer("Действие отменено.")


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext, command: CommandObject):
    await state.clear()
    if not command.args:
        await message.answer(
            "Введите данные нового прокси и его название.\n\n"
            "<b>Формат:</b> <code>host:port:user:pass Название [limit=ГБ] [days=ДНЕЙ]</code>\n\n"
            "<b>Пример:</b>\n<code>proxy.example.com:1234:john:secret123 Прокси1 limit=50 days=30</code>\n\n"
            "Для отмены введите /cancel"
        )
        await state.set_state(ProfileCreation.waiting_for_proxy_details)
        return
    try:
        parts = command.args.split()
        if len(parts) < 2:
            raise ValueError(
                "Неверный формат. Нужно указать и данные прокси, и название."
            )
        proxy_data_str = parts[0]
        parsed_args = parse_args_with_limits(parts[1:])
        remark = parsed_args["remark"]
        if not remark:
            raise ValueError("Необходимо указать название профиля.")
        host, port, user, password = proxy_data_str.split(":")
        await create_proxy_profile(
            message,
            host,
            port,
            user,
            password,
            remark,
            parsed_args["limit"],
            parsed_args["days"],
        )
    except (ValueError, IndexError) as e:
        await message.answer(
            f"❌ <b>Ошибка в формате данных:</b> {e}\n\nИспользуйте формат: <code>/new host:port:user:pass Название [limit=ГБ] [days=ДНЕЙ]</code>"
        )


@router.message(
    ProfileCreation.waiting_for_proxy_details, F.text, ~F.text.startswith("/")
)
async def process_proxy_details_fsm(message: Message, state: FSMContext):
    command = CommandObject(prefix="/", command="new", args=message.text)
    await cmd_new(message, state, command)


@router.message(Command("vless"))
async def cmd_vless(message: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    if not command.args:
        await message.answer(
            "Введите название для обычного VLESS профиля.\n\n"
            "<b>Формат:</b> <code>/vless Название [limit=ГБ] [days=ДНЕЙ]</code>\n\n"
            "<b>Пример:</b>\n<code>/vless Мой телефон limit=10</code>"
        )
        return
    parsed_args = parse_args_with_limits(command.args.split())
    remark = parsed_args["remark"]
    if not remark:
        await message.answer("❌ Необходимо указать название профиля.")
        return
    await create_direct_vless_profile(
        message, remark, parsed_args["limit"], parsed_args["days"]
    )


@router.message(Command("list"))
async def cmd_list(message: Message, state: FSMContext):
    await state.clear()
    text, markup = await get_profiles_markup()
    await message.answer(text, reply_markup=markup)


@router.callback_query(ProfileCallback.filter(F.action == "list"))
async def cq_list_page(query: CallbackQuery, callback_data: ProfileCallback):
    text, markup = await get_profiles_markup(page=callback_data.page)
    await query.message.edit_text(text, reply_markup=markup)
    await query.answer()


@router.callback_query(ProfileCallback.filter(F.action == "confirm_delete"))
async def cq_confirm_delete(query: CallbackQuery, callback_data: ProfileCallback):
    remark = callback_data.profile_id.replace("-", " ")
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="‼️ Да, удалить",
                    callback_data=ProfileCallback(
                        action="execute_delete", profile_id=callback_data.profile_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=ProfileCallback(
                        action="list", page=callback_data.page
                    ).pack(),
                ),
            ]
        ]
    )
    await query.message.edit_text(
        f"Вы уверены, что хотите удалить профиль <b>{remark.capitalize()}</b>?\n\nЭто действие необратимо.",
        reply_markup=markup,
    )
    await query.answer()


@router.callback_query(ProfileCallback.filter(F.action == "execute_delete"))
async def cq_execute_delete(query: CallbackQuery, callback_data: ProfileCallback):
    await query.message.edit_text("Удаляю профиль... ⏳")
    try:
        api = XUIApi(settings.PANEL_URL, settings.PANEL_LOGIN, settings.PANEL_PASSWORD)
        api.login()

        profiles = api.get_profiles(settings.VLESS_INBOUND_ID)
        profile_to_delete = next(
            (p for p in profiles if p["profile_id"] == callback_data.profile_id), None
        )

        if not profile_to_delete:
            raise ValueError("Профиль для удаления не найден.")

        api.delete_profile(
            profile_to_delete["client_remark"],
            profile_to_delete["outbound_tag"],
            settings.VLESS_INBOUND_ID,
        )
        api.restart_xray()

        remark = callback_data.profile_id.replace("-", " ")
        await query.answer(f"Профиль {remark.capitalize()} удален!", show_alert=True)

        text, markup = await get_profiles_markup(page=0)
        await query.message.edit_text(text, reply_markup=markup)
    except Exception as e:
        logging.error(f"Ошибка при удалении: {e}", exc_info=True)
        await query.message.edit_text(f"❌ Не удалось удалить профиль.\nОшибка: {e}")
        await query.answer("Ошибка при удалении", show_alert=True)
