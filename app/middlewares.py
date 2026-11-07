from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.errors import TelegramError
from app.keyboards import join_kb
from app.membership import get_missing_chats, join_prompt

logger = logging.getLogger(__name__)


class IgnoreGroupsMiddleware(BaseMiddleware):
    """Keep the bot completely silent in groups, supergroups and channels.

    The bot may be added to private groups only so it can verify force-join
    membership. It should never reply there, and no command menu is shown.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = None
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message is not None:
            chat = event.message.chat

        if chat is not None and chat.type in {"group", "supergroup", "channel"}:
            return None

        return await handler(event, data)


class DatabaseMiddleware(BaseMiddleware):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            return await handler(event, data)


class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id in settings.admin_ids:
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == "check_join":
            return await handler(event, data)

        message = event if isinstance(event, Message) else event.message
        if message is not None and (message.text or "").startswith("/start"):
            return await handler(event, data)

        session: AsyncSession | None = data.get("session")
        bot: Bot | None = data.get("bot")
        if session is None or bot is None:
            return await handler(event, data)

        missing = await get_missing_chats(bot, session, user.id)
        if not missing:
            return await handler(event, data)

        prompt = join_prompt(missing)
        keyboard = join_kb(missing)
        try:
            if isinstance(event, CallbackQuery):
                await event.answer("Please join the required chats first.", show_alert=True)
                if event.message is not None:
                    await event.message.answer(prompt, reply_markup=keyboard)
            else:
                await event.answer(prompt, reply_markup=keyboard)
        except TelegramError:
            logger.exception("Could not send the join prompt")
        return None
