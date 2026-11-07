from __future__ import annotations

import logging
from html import escape
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

from app.errors import TelegramError

logger = logging.getLogger(__name__)


def esc(value: object) -> str:
    return escape(str(value), quote=False)


def short(value: str, limit: int = 60) -> str:
    value = str(value)
    return value if len(value) <= limit else value[: limit - 1] + "…"


def stock_label(stock: int) -> str:
    if stock < 0:
        return "∞"
    return str(stock)


async def safe_edit(
    message: Any,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    edit = getattr(message, "edit_text", None)
    if not callable(edit):
        try:
            await message.answer(text, reply_markup=reply_markup)
        except TelegramError:
            logger.exception("Could not send fallback message")
        return

    try:
        await edit(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        logger.debug("edit_text failed (%s); sending a new message instead", exc)
        try:
            await message.answer(text, reply_markup=reply_markup)
        except TelegramError:
            logger.exception("Could not send fallback message")
    except TelegramError:
        logger.exception("Could not edit message")


async def safe_send(bot, chat_id: int, text: str, **kwargs) -> bool:
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except TelegramError:
        logger.info("Could not send message to %s", chat_id)
        return False
