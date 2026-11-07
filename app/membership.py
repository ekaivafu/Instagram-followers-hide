from __future__ import annotations

import logging
import time
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import RequiredChat
from app.errors import TelegramError

logger = logging.getLogger(__name__)

_TTL = 45.0
_CACHE: dict[tuple[int, int], tuple[float, bool]] = {}


def clear_user_cache(user_id: int) -> None:
    for key in [key for key in _CACHE if key[0] == user_id]:
        _CACHE.pop(key, None)


async def _is_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    key = (user_id, chat_id)
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]

    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramBadRequest as exc:
        lowered = str(exc).lower()
        if any(
            marker in lowered
            for marker in ("user not found", "participant", "not a member", "member not found")
        ):
            ok = False
        else:
            # Permission/configuration problems should not lock every user out.
            logger.warning("Membership check failed for chat %s: %s (failing open)", chat_id, exc)
            ok = True
    except TelegramError as exc:
        logger.warning("Membership check failed for chat %s: %s (failing open)", chat_id, exc)
        ok = True
    else:
        status = getattr(member, "status", "")
        if status in ("creator", "administrator", "member"):
            ok = True
        elif status == "restricted":
            ok = bool(getattr(member, "is_member", False))
        else:
            ok = False

    if len(_CACHE) > 5000:
        _CACHE.clear()
    _CACHE[key] = (now + _TTL, ok)
    return ok


def join_prompt(chats: list[RequiredChat]) -> str:
    lines = ["🔒 <b>Join required</b>", "", "To use this bot, please join:"]
    for chat in chats:
        lines.append(f"• {escape(chat.title or str(chat.chat_id))}")
    lines.extend(["", "After joining, tap <b>✅ I've joined</b>."])
    return "\n".join(lines)


async def get_missing_chats(bot: Bot, session: AsyncSession, user_id: int) -> list[RequiredChat]:
    chats = (await session.scalars(select(RequiredChat).order_by(RequiredChat.id))).all()
    missing: list[RequiredChat] = []
    for chat in chats:
        if not await _is_member(bot, chat.chat_id, user_id):
            missing.append(chat)
    return missing
