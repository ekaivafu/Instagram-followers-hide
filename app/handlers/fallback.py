from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.keyboards import main_menu_kb

router = Router(name="fallback")


@router.message(StateFilter(None))
async def unknown_message(message: Message) -> None:
    is_admin = bool(message.from_user and message.from_user.id in settings.admin_ids)
    await message.answer(
        "Use the menu below to get started.",
        reply_markup=main_menu_kb(is_admin),
    )


@router.callback_query()
async def stale_callback(callback: CallbackQuery) -> None:
    await callback.answer("This button is no longer active. Send /start to refresh.")
