from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import TelegramError
from app.db import (
    RedeemItem,
    Redemption,
    RequiredChat,
    User,
    get_hide_cost,
    get_referral_points,
    get_welcome_tokens,
    set_setting,
)
from app.filters import IsAdmin
from app.keyboards import (
    admin_back_kb,
    admin_chats_kb,
    admin_home_kb,
    admin_pending_kb,
    admin_referral_kb,
    admin_token_kb,
)
from app.states import AdminFlow
from app.utils import esc, safe_edit, safe_send

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def _as_int(text: str) -> int | None:
    try:
        return int(text.strip())
    except (TypeError, ValueError):
        return None


def forwarded_chat_id(message: Message) -> int | None:
    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        for attribute in ("chat", "sender_chat"):
            chat = getattr(origin, attribute, None)
            if chat is not None:
                return chat.id
    chat = getattr(message, "forward_from_chat", None)
    return chat.id if chat is not None else None


def parse_chat_target(text: str) -> int | str | None:
    value = text.strip()
    if not value:
        return None
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if value.startswith(prefix):
            slug = value[len(prefix):].split("?", 1)[0].strip("/")
            if slug.startswith("+") or slug.startswith("joinchat"):
                return None
            return "@" + slug
    if value.startswith("@"):
        return value
    return _as_int(value)


async def admin_home_text(session: AsyncSession) -> str:
    total_users = await session.scalar(select(func.count()).select_from(User)) or 0
    total_success = await session.scalar(
        select(func.coalesce(func.sum(User.total_success), 0))
    ) or 0
    points_held = await session.scalar(select(func.coalesce(func.sum(User.points), 0))) or 0
    referred = await session.scalar(
        select(func.count()).select_from(User).where(User.referred_by.is_not(None))
    ) or 0
    pending = await session.scalar(
        select(func.count()).select_from(Redemption).where(Redemption.status == "pending")
    ) or 0
    referral_points = await get_referral_points(session)
    hide_cost = await get_hide_cost(session)
    welcome_tokens = await get_welcome_tokens(session)
    chats_count = await session.scalar(select(func.count()).select_from(RequiredChat)) or 0
    items_count = await session.scalar(select(func.count()).select_from(RedeemItem)) or 0

    return (
        "🛠 <b>Admin Panel</b>\n\n"
        f"👥 Users: <b>{total_users}</b>\n"
        f"✅ Successful hides: <b>{total_success}</b>\n"
        f"🪙 Tokens held by users: <b>{points_held}</b>\n"
        f"🔗 Referred users: <b>{referred}</b>\n"
        f"⏳ Pending redemptions: <b>{pending}</b>\n\n"
        f"⚙️ Referral reward: <b>{referral_points}</b> per invite\n"
        f"💵 Hide cost: <b>{hide_cost}</b> per hide\n"
        f"🎁 Welcome bonus: <b>{welcome_tokens}</b> for new users\n"
        f"📢 Required chats: <b>{chats_count}</b>\n"
        f"🎁 Redeem items: <b>{items_count}</b>"
    )


async def chats_view(session: AsyncSession) -> tuple[str, list[RequiredChat]]:
    chats = list(
        (await session.scalars(select(RequiredChat).order_by(RequiredChat.id))).all()
    )
    lines = [
        "📢 <b>Required Chats</b>",
        "",
        "Users must join all of these before they can use the bot.",
        "",
    ]
    if not chats:
        lines.append("No chats added yet.")
    for chat in chats:
        link = chat.invite_link or (f"https://t.me/{chat.username}" if chat.username else "no link")
        lines.append(
            f"• <b>{esc(chat.title)}</b> ({esc(chat.kind)})\n"
            f"  ID: <code>{chat.chat_id}</code>\n"
            f"  {esc(link)}"
        )
    lines.append("")
    lines.append("⚠️ The bot must be an administrator in each chat.")
    return "\n".join(lines), chats


def referral_view(points: int, hide_cost: int, welcome_tokens: int) -> str:
    return (
        "⚙️ <b>Token Settings</b>\n\n"
        f"🔗 Referral reward: <b>{points}</b> token(s) per invite\n"
        f"💵 Hide cost: <b>{hide_cost}</b> token(s) per hide\n"
        f"🎁 Welcome bonus: <b>{welcome_tokens}</b> token(s) for new users\n\n"
        "A referral is credited when an invited user completes their first "
        "successful hide. Set a value to 0 to disable it."
    )


async def _token_settings(session: AsyncSession) -> tuple[int, int, int]:
    return (
        await get_referral_points(session),
        await get_hide_cost(session),
        await get_welcome_tokens(session),
    )


async def pending_view(session: AsyncSession) -> tuple[str, list[Redemption]]:
    pending = list(
        (
            await session.scalars(
                select(Redemption)
                .where(Redemption.status == "pending")
                .order_by(Redemption.id.desc())
                .limit(20)
            )
        ).all()
    )
    lines = ["⏳ <b>Pending Redemptions</b>", ""]
    if not pending:
        lines.append("Nothing pending. 🎉")
    else:
        lines.append("Tap a request to mark it completed.")
        for redemption in pending:
            created = redemption.created_at.strftime("%d %b %Y %H:%M") if redemption.created_at else "—"
            lines.append(
                f"• <b>#{redemption.id}</b> — {esc(redemption.item_title)}\n"
                f"  User: <code>{redemption.user_id}</code> · {redemption.cost} pts · {created}"
            )
    return "\n".join(lines), pending


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await message.answer(await admin_home_text(session), reply_markup=admin_home_kb())


@router.message(Command("cancel"))
async def cmd_admin_cancel(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await message.answer(
        "✅ Cancelled.\n\n" + await admin_home_text(session),
        reply_markup=admin_home_kb(),
    )


@router.callback_query(F.data == "adm:home")
async def adm_home(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await safe_edit(callback.message, await admin_home_text(session), admin_home_kb())


@router.callback_query(F.data == "adm:chats")
async def adm_chats(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    text, chats = await chats_view(session)
    await safe_edit(callback.message, text, admin_chats_kb(chats))


@router.callback_query(F.data == "adm:chat:add")
async def adm_chat_add(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(AdminFlow.chat)
    if callback.message is not None:
        await safe_edit(
            callback.message,
            "➕ <b>Add required chat</b>\n\n"
            "Send one of these:\n"
            "• <code>@username</code> of the channel/group\n"
            "• numeric chat ID (e.g. <code>-1001234567890</code>)\n"
            "• forward any message from that channel/group\n\n"
            "⚠️ The bot must be an administrator there so it can verify members "
            "and create an invite link.\n\n"
            "Send /cancel to abort.",
            admin_back_kb("adm:chats"),
        )


@router.message(AdminFlow.chat)
async def adm_chat_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    target = forwarded_chat_id(message)
    if target is None:
        target = parse_chat_target(message.text or "")
    if target is None:
        await message.answer(
            "❌ I couldn't recognise that chat. Send @username, a numeric chat ID, "
            "or forward a message from the chat.",
            reply_markup=admin_back_kb("adm:chats"),
        )
        return

    try:
        chat = await bot.get_chat(target)
    except TelegramError as exc:
        await message.answer(f"❌ Could not find that chat: {esc(exc)}")
        return

    if chat.type not in ("channel", "group", "supergroup"):
        await message.answer("❌ Only channels and groups can be required chats.")
        return

    me = await bot.get_me()
    try:
        member = await bot.get_chat_member(chat.id, me.id)
    except TelegramError as exc:
        await message.answer(
            "❌ I couldn't check my permissions in that chat. Add me as an "
            f"administrator first.\n\n<code>{esc(exc)}</code>"
        )
        return

    if member.status not in ("administrator", "creator"):
        await message.answer(
            "❌ I must be an administrator in that channel/group before it can be "
            "used for force-join."
        )
        return

    invite_link = None
    try:
        link = await bot.create_chat_invite_link(chat_id=chat.id, name="Bot access")
        invite_link = link.invite_link
    except TelegramError:
        invite_link = None

    if not chat.username and not invite_link:
        await message.answer(
            "❌ This is a private chat and I couldn't create an invite link. "
            "Give me the <i>Invite users</i> permission, then try again."
        )
        return

    existing = await session.scalar(select(RequiredChat).where(RequiredChat.chat_id == chat.id))
    if existing is not None:
        existing.title = chat.title or str(chat.id)
        existing.username = chat.username
        existing.invite_link = invite_link or existing.invite_link
        existing.kind = chat.type
        notice = "♻️ Updated required chat."
    else:
        session.add(
            RequiredChat(
                chat_id=chat.id,
                title=chat.title or str(chat.id),
                username=chat.username,
                invite_link=invite_link,
                kind=chat.type,
            )
        )
        notice = "✅ Added required chat."

    await session.commit()
    await state.clear()

    text, chats = await chats_view(session)
    await message.answer(
        f"{notice}\n\n<b>{esc(chat.title or chat.id)}</b>\n\n{text}",
        reply_markup=admin_chats_kb(chats),
    )


@router.callback_query(F.data.startswith("adm:chat:del:"))
async def adm_chat_delete(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    await state.clear()
    try:
        row_id = int((callback.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return

    chat = await session.get(RequiredChat, row_id)
    if chat is None:
        return
    title = chat.title
    await session.delete(chat)
    await session.commit()

    if callback.message is not None:
        text, chats = await chats_view(session)
        await safe_edit(
            callback.message,
            f"🗑 Removed <b>{esc(title)}</b>.\n\n{text}",
            admin_chats_kb(chats),
        )


@router.callback_query(F.data == "adm:referral")
async def adm_referral(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await safe_edit(
            callback.message,
            referral_view(*await _token_settings(session)),
            admin_referral_kb(),
        )


@router.callback_query(F.data == "adm:referral:edit")
async def adm_referral_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(AdminFlow.referral_points)
    if callback.message is not None:
        await safe_edit(
            callback.message,
            "✏️ Send the new number of tokens awarded per successful referral "
            "(0 or more).\n\nSend /cancel to abort.",
            admin_back_kb("adm:referral"),
        )


@router.message(AdminFlow.referral_points, F.text)
async def adm_referral_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    value = _as_int(message.text or "")
    if value is None or value < 0 or value > 1_000_000:
        await message.answer("❌ Send a whole number between 0 and 1,000,000.")
        return

    await set_setting(session, "referral_points", value)
    await state.clear()
    await message.answer(
        referral_view(*await _token_settings(session)),
        reply_markup=admin_referral_kb(),
    )


@router.callback_query(F.data == "adm:referral:cost")
async def adm_referral_cost(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(AdminFlow.hide_cost)
    if callback.message is not None:
        await safe_edit(
            callback.message,
            "✏️ Send the number of tokens a hide should cost (0 or more).\n"
            "Set 0 to make hiding free.\n\nSend /cancel to abort.",
            admin_back_kb("adm:referral"),
        )


@router.message(AdminFlow.hide_cost, F.text)
async def adm_referral_cost_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    value = _as_int(message.text or "")
    if value is None or value < 0 or value > 1_000_000:
        await message.answer("❌ Send a whole number between 0 and 1,000,000.")
        return

    await set_setting(session, "hide_cost", value)
    await state.clear()
    await message.answer(
        referral_view(*await _token_settings(session)),
        reply_markup=admin_referral_kb(),
    )


@router.callback_query(F.data == "adm:referral:welcome")
async def adm_referral_welcome(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(AdminFlow.welcome_tokens)
    if callback.message is not None:
        await safe_edit(
            callback.message,
            "✏️ Send the number of tokens every new user receives on signup "
            "(0 or more).\n\nSend /cancel to abort.",
            admin_back_kb("adm:referral"),
        )


@router.message(AdminFlow.welcome_tokens, F.text)
async def adm_referral_welcome_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    value = _as_int(message.text or "")
    if value is None or value < 0 or value > 1_000_000:
        await message.answer("❌ Send a whole number between 0 and 1,000,000.")
        return

    await set_setting(session, "welcome_tokens", value)
    await state.clear()
    await message.answer(
        referral_view(*await _token_settings(session)),
        reply_markup=admin_referral_kb(),
    )


@router.callback_query(F.data == "adm:points")
async def adm_points(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(AdminFlow.points_user_id)
    if callback.message is not None:
        await safe_edit(
            callback.message,
            "🪙 <b>Give Tokens</b>\n\nSend the Telegram user ID whose tokens you "
            "want to add or change.\n\nSend /cancel to abort.",
            admin_back_kb("adm:home"),
        )


@router.message(AdminFlow.points_user_id, F.text)
async def adm_points_user(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user_id = _as_int(message.text or "")
    if user_id is None:
        await message.answer("❌ Send a numeric Telegram user ID.")
        return

    user = await session.get(User, user_id)
    if user is None:
        await message.answer("❌ No user with that ID has started the bot.")
        return

    await state.clear()
    username = f"@{user.username}" if user.username else "no username"
    await message.answer(
        f"👤 <b>{esc(user.first_name or 'User')}</b> ({esc(username)})\n"
        f"ID: <code>{user.user_id}</code>\n"
        f"Current tokens: <b>{user.points}</b>\n\n"
        "Choose what to do:",
        reply_markup=admin_token_kb(user.user_id),
    )


@router.callback_query(F.data.startswith("adm:points:add:"))
async def adm_points_add(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    try:
        user_id = int((callback.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return

    user = await session.get(User, user_id)
    if user is None or callback.message is None:
        await safe_edit(callback.message, "❌ User not found.", admin_home_kb())
        return

    await state.clear()
    await state.update_data(target_user=user.user_id)
    await state.set_state(AdminFlow.points_add_value)
    await safe_edit(
        callback.message,
        f"➕ <b>Add tokens</b>\n\n"
        f"User: <code>{user.user_id}</code>\n"
        f"Current tokens: <b>{user.points}</b>\n\n"
        "Send how many tokens to add (1 or more).\n\nSend /cancel to abort.",
        admin_back_kb("adm:home"),
    )


@router.callback_query(F.data.startswith("adm:points:set:"))
async def adm_points_set(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    try:
        user_id = int((callback.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return

    user = await session.get(User, user_id)
    if user is None or callback.message is None:
        await safe_edit(callback.message, "❌ User not found.", admin_home_kb())
        return

    await state.clear()
    await state.update_data(target_user=user.user_id)
    await state.set_state(AdminFlow.points_value)
    await safe_edit(
        callback.message,
        f"✏️ <b>Set exact balance</b>\n\n"
        f"User: <code>{user.user_id}</code>\n"
        f"Current tokens: <b>{user.points}</b>\n\n"
        "Send the new token balance (0 or more).\n\nSend /cancel to abort.",
        admin_back_kb("adm:home"),
    )


@router.message(AdminFlow.points_add_value, F.text)
async def adm_points_add_value(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    value = _as_int(message.text or "")
    if value is None or value < 1 or value > 100_000_000:
        await message.answer("❌ Send a whole number between 1 and 100,000,000.")
        return

    data = await state.get_data()
    user_id = data.get("target_user")
    user = await session.get(User, int(user_id)) if user_id else None
    if user is None:
        await state.clear()
        await message.answer("❌ User no longer exists.", reply_markup=admin_home_kb())
        return

    user.points += value
    await session.commit()
    await session.refresh(user)
    await state.clear()

    await message.answer(
        f"✅ Added <b>{value}</b> tokens to <code>{user.user_id}</code>.\n"
        f"New balance: <b>{user.points}</b>.",
        reply_markup=admin_home_kb(),
    )
    await safe_send(
        bot,
        user.user_id,
        "🪙 <b>Tokens received</b>\n\n"
        f"An admin added <b>{value} tokens</b> to your balance.\n"
        f"⭐ Your tokens: <b>{user.points}</b>",
    )


@router.message(AdminFlow.points_value, F.text)
async def adm_points_value(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    value = _as_int(message.text or "")
    if value is None or value < 0 or value > 100_000_000:
        await message.answer("❌ Send a whole number between 0 and 100,000,000.")
        return

    data = await state.get_data()
    user_id = data.get("target_user")
    user = await session.get(User, int(user_id)) if user_id else None
    if user is None:
        await state.clear()
        await message.answer("❌ User no longer exists.", reply_markup=admin_home_kb())
        return

    old = user.points
    user.points = value
    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ Updated <code>{user.user_id}</code>: {old} → <b>{value}</b> tokens.",
        reply_markup=admin_home_kb(),
    )
    if old != value:
        await safe_send(
            bot,
            user.user_id,
            f"🪙 An admin adjusted your tokens: <b>{value}</b>.",
        )


@router.callback_query(F.data == "adm:pending")
async def adm_pending(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    text, pending = await pending_view(session)
    await safe_edit(callback.message, text, admin_pending_kb(pending))


@router.callback_query(F.data.startswith("adm:fulfill:"))
async def adm_fulfill(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return
    try:
        redemption_id = int((callback.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return

    redemption = await session.get(Redemption, redemption_id)
    if redemption is None or redemption.status != "pending":
        text, pending = await pending_view(session)
        await safe_edit(callback.message, "⚠️ Already handled.\n\n" + text, admin_pending_kb(pending))
        return

    redemption.status = "completed"
    redemption.fulfilled_by = callback.from_user.id
    await session.commit()

    await safe_send(
        bot,
        redemption.user_id,
        f"🎁 <b>Redemption completed</b>\n\n"
        f"Item: <b>{esc(redemption.item_title)}</b>\n"
        "Your reward is ready. Contact an admin if you have not received it.",
    )

    text, pending = await pending_view(session)
    await safe_edit(
        callback.message,
        f"✅ Completed request <b>#{redemption_id}</b>.\n\n{text}",
        admin_pending_kb(pending),
    )
