from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)

from app.config import settings

logger = logging.getLogger(__name__)

BASE_COMMANDS = [
    BotCommand(command="start", description="Start the bot"),
    BotCommand(command="hide", description="Hide followers & following"),
    BotCommand(command="refer", description="Get your referral link"),
    BotCommand(command="redeem", description="Redeem your points"),
    BotCommand(command="profile", description="Your stats"),
    BotCommand(command="help", description="How to use the bot"),
    BotCommand(command="cancel", description="Cancel the current action"),
]

ADMIN_COMMAND = BotCommand(command="admin", description="Admin panel")


async def set_default_commands(bot: Bot) -> None:
    # Default fallback (also clears any old unscoped command list).
    await bot.set_my_commands(BASE_COMMANDS, scope=BotCommandScopeDefault())
    # Full menu in private chats only.
    await bot.set_my_commands(BASE_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    # No command menu in groups/supergroups, even though the bot stays there
    # so it can check force-join membership.
    await bot.set_my_commands([], scope=BotCommandScopeAllGroupChats())


async def set_admin_commands_for(bot: Bot, admin_id: int) -> bool:
    """Register /admin for one admin. Fails until that admin has started the bot."""
    try:
        await bot.set_my_commands(
            BASE_COMMANDS + [ADMIN_COMMAND],
            scope=BotCommandScopeChat(chat_id=admin_id),
        )
        return True
    except TelegramAPIError:
        return False


async def setup_commands(bot: Bot) -> None:
    await set_default_commands(bot)
    for admin_id in settings.admin_ids:
        if not await set_admin_commands_for(bot, admin_id):
            logger.info(
                "Could not set admin commands for %s yet; it will be retried when they send /start.",
                admin_id,
            )
