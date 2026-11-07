from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import RedeemItem, Redemption, User, get_referral_points
from app.keyboards import (
    back_kb,
    pending_hint_kb,
    redeem_item_kb,
    redeem_list_kb,
    refer_kb,
)
from app.services import referral_counts, referral_link, register_user
from app.utils import esc, safe_edit, safe_send, stock_label

router = Router(name="referral")


async def _refer_text(session: AsyncSession, user: User) -> str:
    points = await get_referral_points(session)
    total_refs, credited_refs = await referral_counts(session, user.user_id)
    token_word = "token" if points == 1 else "tokens"
    balance = (
        "♾ Unlimited (admin)"
        if user.user_id in settings.admin_ids
        else f"<b>{user.points}</b>"
    )
    return (
        "👥 <b>Refer &amp; Earn</b>\n\n"
        f"Your link:\n<code>{esc(referral_link(user.user_id))}</code>\n\n"
        "Share it with friends. When a friend joins and completes their first hide, "
        f"you receive <b>{points} {token_word}</b>.\n\n"
        f"⭐ Your tokens: {balance}\n"
        f"👤 Friends joined: {total_refs}\n"
        f"✅ Friends who completed a hide: {credited_refs}\n\n"
        "💵 Tokens are used to hide accounts and can also be redeemed for rewards."
    )


@router.message(Command("refer"))
async def cmd_refer(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user, _ = await register_user(session, message.from_user)
    await message.answer(
        await _refer_text(session, user),
        reply_markup=refer_kb(referral_link(user.user_id)),
    )


@router.callback_query(F.data == "menu:refer")
async def menu_refer(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    await state.clear()
    if callback.from_user is None or callback.message is None:
        return
    user, _ = await register_user(session, callback.from_user)
    await safe_edit(
        callback.message,
        await _refer_text(session, user),
        refer_kb(referral_link(user.user_id)),
    )


async def _redeem_list_text(session: AsyncSession, user: User) -> tuple[str, list[RedeemItem]]:
    items = (
        await session.scalars(
            select(RedeemItem)
            .where(RedeemItem.active.is_(True))
            .order_by(RedeemItem.cost, RedeemItem.id)
        )
    ).all()
    lines = [
        "🎁 <b>Redeem Tokens</b>",
        "",
        "⭐ Your tokens: "
        + (
            "♾ Unlimited (admin)"
            if user.user_id in settings.admin_ids
            else f"<b>{user.points}</b>"
        ),
        "",
    ]
    if not items:
        lines.append("No rewards are available right now. Check back later!")
    else:
        lines.append("Choose a reward:")
        for item in items:
            stock = "unlimited" if item.stock < 0 else f"{item.stock} left"
            lines.append(f"• <b>{esc(item.title)}</b> — {item.cost} tokens ({stock})")
    return "\n".join(lines), list(items)


@router.message(Command("redeem"))
async def cmd_redeem(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user, _ = await register_user(session, message.from_user)
    text, items = await _redeem_list_text(session, user)
    await message.answer(text, reply_markup=redeem_list_kb(items) if items else back_kb())


@router.callback_query(F.data == "menu:redeem")
async def menu_redeem(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    await state.clear()
    if callback.from_user is None or callback.message is None:
        return
    user, _ = await register_user(session, callback.from_user)
    text, items = await _redeem_list_text(session, user)
    await safe_edit(
        callback.message,
        text,
        redeem_list_kb(items) if items else back_kb(),
    )


@router.callback_query(F.data.startswith("redeem:item:"))
async def redeem_item_view(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    try:
        item_id = int((callback.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        await safe_edit(callback.message, "❌ Reward not found.", back_kb())
        return

    item = await session.get(RedeemItem, item_id)
    if item is None or not item.active:
        await safe_edit(callback.message, "❌ This reward is no longer available.", back_kb())
        return

    deliver = (
        "⚡ Delivered automatically after redeeming."
        if item.delivery_type == "auto"
        else "👤 An admin will deliver it manually."
    )
    text = (
        f"🎁 <b>{esc(item.title)}</b>\n\n"
        f"{esc(item.description) if item.description else 'No description.'}\n\n"
        f"💵 Cost: <b>{item.cost} tokens</b>\n"
        f"📦 Stock: {stock_label(item.stock)}\n"
        f"{deliver}"
    )
    await safe_edit(callback.message, text, redeem_item_kb(item))


@router.callback_query(F.data.startswith("redeem:buy:"))
async def redeem_buy(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    try:
        item_id = int((callback.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Invalid reward.", show_alert=True)
        return

    item = await session.get(RedeemItem, item_id)
    user = await session.get(User, callback.from_user.id)

    if item is None or not item.active:
        await callback.answer("This reward is no longer available.", show_alert=True)
        return
    if item.stock == 0:
        await callback.answer("This reward is out of stock.", show_alert=True)
        return
    if user is None:
        await callback.answer("Please send /start first.", show_alert=True)
        return
    is_admin = callback.from_user.id in settings.admin_ids
    if not is_admin:
        if user.points < item.cost:
            await callback.answer(
                f"You need {item.cost - user.points} more tokens.", show_alert=True
            )
            return

        # Atomic deduction so double-taps cannot spend the same tokens twice.
        points_result = await session.execute(
            update(User)
            .where(User.user_id == user.user_id, User.points >= item.cost)
            .values(points=User.points - item.cost)
        )
        if points_result.rowcount != 1:
            await session.rollback()
            await callback.answer("You do not have enough tokens.", show_alert=True)
            return

    if item.stock > 0:
        stock_result = await session.execute(
            update(RedeemItem)
            .where(RedeemItem.id == item.id, RedeemItem.stock > 0)
            .values(stock=RedeemItem.stock - 1)
        )
        if stock_result.rowcount != 1:
            await session.rollback()
            await callback.answer("This reward just went out of stock.", show_alert=True)
            return

    redemption = Redemption(
        user_id=user.user_id,
        item_id=item.id,
        item_title=item.title,
        cost=item.cost,
        status="completed" if item.delivery_type == "auto" else "pending",
    )
    session.add(redemption)
    await session.commit()
    await session.refresh(redemption)
    await session.refresh(user)
    await callback.answer()

    tokens_left = "♾ Unlimited (admin)" if is_admin else f"<b>{user.points}</b>"

    if item.delivery_type == "auto":
        reward = item.reward_text or "Please contact an admin to receive your reward."
        text = (
            f"✅ <b>Redeemed: {esc(item.title)}</b>\n\n"
            f"💵 Spent: {item.cost} tokens\n"
            f"⭐ Tokens left: {tokens_left}\n\n"
            f"🎁 <b>Your reward</b>\n{esc(reward)}"
        )
    else:
        text = (
            f"✅ <b>Request submitted: {esc(item.title)}</b>\n\n"
            f"💵 Spent: {item.cost} tokens\n"
            f"⭐ Tokens left: {tokens_left}\n\n"
            "👤 An admin will deliver your reward soon."
        )
        username = f"@{user.username}" if user.username else "no username"
        notification = (
            "🔔 <b>New manual redemption</b>\n\n"
            f"Request: <code>#{redemption.id}</code>\n"
            f"User: <code>{user.user_id}</code> ({esc(username)})\n"
            f"Item: <b>{esc(item.title)}</b>\n"
            f"Cost: {item.cost} tokens"
        )
        for admin_id in settings.admin_ids:
            await safe_send(bot, admin_id, notification, reply_markup=pending_hint_kb())

    await safe_edit(callback.message, text, back_kb())
