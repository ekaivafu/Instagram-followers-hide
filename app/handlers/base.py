from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.commands import set_admin_commands_for
from app.config import settings
from app.db import User, get_hide_cost, get_welcome_tokens
from app.filters import IsAdmin
from app.keyboards import back_kb, join_kb, main_menu_kb
from app.membership import clear_user_cache, get_missing_chats, join_prompt
from app.services import credit_referral_if_due, referral_counts, register_user
from app.utils import esc, safe_edit

router = Router(name="base")


def welcome_text(
    first_name: str,
    points: int,
    cost: int,
    bonus: int = 0,
    unlimited: bool = False,
) -> str:
    token_word = "token" if cost == 1 else "tokens"
    balance = "♾ Unlimited (admin)" if unlimited else f"<b>{points}</b>"
    text = (
        f"👋 <b>Welcome, {esc(first_name or 'there')}!</b>\n\n"
        "This bot hides your Instagram followers &amp; following lists.\n\n"
        "• Tap <b>Hide Followers &amp; Following</b>\n"
        "• Send your <code>sessionid</code> cookie value\n"
        "• The message is deleted right away and your lists are hidden\n\n"
        f"💵 Each hide costs <b>{cost} {token_word}</b>.\n"
        f"⭐ Your tokens: {balance}"
    )
    if bonus > 0:
        text += f"\n🎁 Welcome bonus: <b>+{bonus}</b>"
    text += (
        "\n\nInvite friends to earn tokens. You receive tokens as soon as a friend "
        "joins the bot with your referral link."
    )
    if settings.support_username:
        text += f"\n\n💬 Need help? Contact {esc(settings.support_username)}"
    return text


async def welcome_for(session: AsyncSession, user: User, created: bool) -> str:
    cost = await get_hide_cost(session)
    bonus = await get_welcome_tokens(session) if created else 0
    unlimited = user.user_id in settings.admin_ids
    return welcome_text(user.first_name or "", user.points, cost, bonus, unlimited)


def profile_text(user: User, total_refs: int, credited_refs: int) -> str:
    joined = user.created_at.strftime("%d %b %Y") if user.created_at else "—"
    tokens = (
        "♾ Unlimited (admin)"
        if user.user_id in settings.admin_ids
        else f"<b>{user.points}</b>"
    )
    return (
        "👤 <b>My Profile</b>\n\n"
        f"🆔 User ID: <code>{user.user_id}</code>\n"
        f"⭐ Tokens: {tokens}\n"
        f"✅ Successful hides: {user.total_success}\n"
        f"👥 Friends joined: {total_refs}\n"
        f"🎁 Friends who earned you tokens: {credited_refs}\n"
        f"📅 Joined: {joined}\n\n"
        "💵 Tokens are used to hide accounts and can also be redeemed for rewards."
    )


def help_text() -> str:
    text = (
        "❓ <b>How to use</b>\n\n"
        "<b>1. Hide your lists</b>\n"
        "Tap <b>Hide Followers &amp; Following</b>, then send your Instagram "
        "<code>sessionid</code> cookie value. Each successful hide uses tokens.\n\n"
        "<b>2. How to get your sessionid (PC)</b>\n"
        "Open <b>instagram.com</b> and log in → <b>right-click</b> → "
        "<b>Inspect</b> → <b>Application</b> tab → <b>Storage → Cookies → "
        "https://www.instagram.com</b> → copy the <b>Value</b> of <b>sessionid</b>.\n"
        "Copy only the value, not <code>sessionid=</code>.\n"
        "📱 Mobile won't work — use a PC or laptop.\n\n"
        "<b>3. Refer &amp; earn</b>\n"
        "Share your referral link. As soon as a friend joins the bot through your "
        "link, you receive tokens automatically.\n\n"
        "<b>4. Redeem</b>\n"
        "Use tokens to claim rewards from the redeem menu.\n\n"
        "🔒 Your sessionid message is deleted immediately. For extra safety, use a "
        "secondary account and change your password afterwards."
    )
    if settings.support_username:
        text += f"\n\n💬 Need help? Contact {esc(settings.support_username)}"
    return text


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    await state.clear()
    if message.from_user is None:
        return

    payload = (message.text or "").split(maxsplit=1)
    arg = payload[1].strip() if len(payload) > 1 else ""
    referral_id: int | None = None
    if arg.startswith("ref_"):
        try:
            referral_id = int(arg[4:])
        except ValueError:
            referral_id = None

    user, created = await register_user(session, message.from_user, referral_id)

    is_admin = message.from_user.id in settings.admin_ids
    if is_admin:
        await set_admin_commands_for(bot, message.from_user.id)

    missing = [] if is_admin else await get_missing_chats(bot, session, message.from_user.id)
    if missing:
        await message.answer(join_prompt(missing), reply_markup=join_kb(missing))
        return

    # The invited user just joined (or finished force-join): pay the referrer now.
    await credit_referral_if_due(bot, session, user)

    await message.answer(
        await welcome_for(session, user, created),
        reply_markup=main_menu_kb(is_admin),
    )


@router.callback_query(F.data == "check_join")
async def check_join(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return

    clear_user_cache(callback.from_user.id)
    missing = await get_missing_chats(bot, session, callback.from_user.id)
    if missing:
        await safe_edit(callback.message, join_prompt(missing), join_kb(missing))
        return

    await state.clear()
    user, created = await register_user(session, callback.from_user)
    await credit_referral_if_due(bot, session, user)
    is_admin = callback.from_user.id in settings.admin_ids
    await safe_edit(
        callback.message,
        "✅ <b>Verified!</b>\n\n" + await welcome_for(session, user, created),
        main_menu_kb(is_admin),
    )


@router.callback_query(F.data == "menu:home")
async def menu_home(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    await state.clear()
    if callback.from_user is None or callback.message is None:
        return
    user, created = await register_user(session, callback.from_user)
    is_admin = callback.from_user.id in settings.admin_ids
    await safe_edit(
        callback.message,
        await welcome_for(session, user, created),
        main_menu_kb(is_admin),
    )


@router.callback_query(F.data == "menu:profile")
async def menu_profile(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    await state.clear()
    if callback.from_user is None or callback.message is None:
        return

    user, _ = await register_user(session, callback.from_user)
    total_refs, credited_refs = await referral_counts(session, user.user_id)
    await safe_edit(
        callback.message,
        profile_text(user, total_refs, credited_refs),
        back_kb(),
    )


@router.callback_query(F.data == "menu:help")
async def menu_help(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    await safe_edit(callback.message, help_text(), back_kb())


@router.message(Command("profile"))
async def cmd_profile(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user, _ = await register_user(session, message.from_user)
    total_refs, credited_refs = await referral_counts(session, user.user_id)
    await message.answer(profile_text(user, total_refs, credited_refs), reply_markup=back_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(help_text(), reply_markup=back_kb())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    is_admin = bool(message.from_user and message.from_user.id in settings.admin_ids)
    await message.answer("✅ Cancelled.", reply_markup=main_menu_kb(is_admin))


@router.message(Command("admin"), ~IsAdmin())
async def admin_denied(message: Message) -> None:
    await message.answer("⛔ This command is only available to administrators.")
