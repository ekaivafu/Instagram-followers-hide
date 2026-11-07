from __future__ import annotations

import asyncio
import logging
import signal
from urllib.parse import urlsplit

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

from app import context
from app.commands import setup_commands
from app.config import settings
from app.db import configure_database, dispose_database, init_db
from app.handlers import (
    admin_items_router,
    admin_router,
    base_router,
    fallback_router,
    hide_router,
    referral_router,
)
from app.middlewares import (
    DatabaseMiddleware,
    ForceJoinMiddleware,
    IgnoreGroupsMiddleware,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("bot")


def build_dispatcher(session_factory) -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())

    # Drop group/channel updates before anything else, so the bot stays silent.
    dispatcher.message.middleware(IgnoreGroupsMiddleware())
    dispatcher.callback_query.middleware(IgnoreGroupsMiddleware())
    dispatcher.message.middleware(DatabaseMiddleware(session_factory))
    dispatcher.callback_query.middleware(DatabaseMiddleware(session_factory))
    dispatcher.message.middleware(ForceJoinMiddleware())
    dispatcher.callback_query.middleware(ForceJoinMiddleware())

    # Commands and menu callbacks first, then stateful admin flows, then fallback.
    dispatcher.include_routers(
        base_router,
        hide_router,
        referral_router,
        admin_router,
        admin_items_router,
        fallback_router,
    )
    return dispatcher


async def prepare(bot: Bot) -> None:
    await init_db()
    me = await bot.get_me()
    context.bot_username = me.username or ""
    logger.info("Bot username: @%s", context.bot_username)
    if not settings.admin_ids:
        logger.warning("ADMIN_IDS is empty; the /admin panel is disabled.")

    await setup_commands(bot)


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def run_webhook(bot: Bot, dispatcher: Dispatcher) -> None:
    app = web.Application()
    webhook_path = urlsplit(settings.webhook_url or "").path or "/webhook"

    handler = SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=settings.webhook_secret,
    )
    handler.register(app, path=webhook_path)
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=settings.port)
    await site.start()

    await bot.set_webhook(
        settings.webhook_url,
        secret_token=settings.webhook_secret,
        drop_pending_updates=False,
        allowed_updates=dispatcher.resolve_used_update_types(),
    )
    logger.info("Webhook listening on %s:%s%s", "0.0.0.0", settings.port, webhook_path)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass

    try:
        await stop.wait()
    finally:
        await bot.delete_webhook()
        await runner.cleanup()


async def main() -> None:
    session_factory = configure_database(settings.database_url)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )
    dispatcher = build_dispatcher(session_factory)

    try:
        await prepare(bot)
        if settings.webhook_url:
            await run_webhook(bot, dispatcher)
        else:
            await bot.delete_webhook(drop_pending_updates=False)
            logger.info("Polling mode")
            await dispatcher.start_polling(
                bot,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )
    finally:
        await bot.session.close()
        await dispose_database()


if __name__ == "__main__":
    asyncio.run(main())
