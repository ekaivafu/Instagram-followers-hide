from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import User, get_hide_cost, get_referral_points
from app.instagram import hide_lists, instagram_user_id
from app.keyboards import low_credit_kb
from app.services import register_user
from app.states import HideFlow
from app.utils import esc, safe_send

logger = logging.getLogger(__name__)
router = Router(name="hide")

HELP_LINE = (
    f"\n\n💬 Need help? Contact {esc(settings.support_username)}"
    if settings.support_username
    else ""
)


def _token_word(count: int) -> str:
    return "token" if count == 1 else "tokens"


def _is_unlimited(user_id: int | None) -> bool:
    return bool(user_id is not None and user_id in settings.admin_ids)


def low_credit_text(points: int, cost: int) -> str:
    text = (
        "🚫 <b>Not enough tokens</b>\n\n"
        f"A hide costs <b>{cost} {_token_word(cost)}</b>, "
        f"but your balance is <b>{points}</b>.\n\n"
        "How to get tokens:\n"
        "• Invite friends — you earn tokens when they complete their first hide\n"
        "• Redeem rewards with your tokens\n"
    )
    if settings.support_username:
        text += f"\n💰 Want tokens? Contact {esc(settings.support_username)}"
    else:
        text += "\n💰 Want tokens? Contact an admin."
    return text


def instruction_text(cost: int, balance: int, unlimited: bool = False) -> str:
    balance_line = (
        "♾ Unlimited (admin)"
        if unlimited
        else f"<b>{cost} {_token_word(cost)}</b> · Your balance: <b>{balance}</b>"
    )
    charge_line = (
        "Admin accounts hide for free.\n\n"
        if unlimited
        else "The token is charged only if the hide succeeds.\n\n"
    )
    return (
        "🔐 <b>Hide Followers &amp; Following</b>\n\n"
        f"💵 Cost: {balance_line}\n"
        f"{charge_line}"
        "Send your Instagram <code>sessionid</code> cookie value.\n\n"
        "💻 <b>How to get your sessionid on PC / laptop:</b>\n\n"
        "1. Open <b>instagram.com</b> in Chrome/Edge and log in to your account.\n"
        "2. <b>Right-click</b> anywhere on the page and click <b>Inspect</b>.\n"
        "3. Open the <b>Application</b> tab at the top of Developer Tools.\n"
        "   (If you don't see it, click the <b>&gt;&gt;</b> arrow.)\n"
        "4. On the left, open <b>Storage → Cookies → https://www.instagram.com</b>.\n"
        "5. Find the cookie named <b>sessionid</b> in the list.\n"
        "6. Copy only its <b>Value</b>.\n"
        "   ⚠️ Copy only the value — do not include <code>sessionid=</code>.\n"
        "7. Paste the value here and send it.\n\n"
        "📱 The sessionid cannot be copied from mobile — use a PC or laptop.\n\n"
        "🔒 Your message is deleted as soon as it is read."
        f"{HELP_LINE}"
    )


def _credit_keyboard():
    return low_credit_kb(settings.support_username)


@router.callback_query(F.data == "hide:start")
async def hide_start_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return

    user, _ = await register_user(session, callback.from_user)
    cost = await get_hide_cost(session)
    unlimited = _is_unlimited(callback.from_user.id)

    if not unlimited and user.points < cost:
        await callback.message.answer(
            low_credit_text(user.points, cost),
            reply_markup=_credit_keyboard(),
        )
        return

    await state.set_state(HideFlow.waiting_for_sessionid)
    await callback.message.answer(instruction_text(cost, user.points, unlimited))


@router.message(Command("hide"))
async def hide_start_command(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        return

    user, _ = await register_user(session, message.from_user)
    cost = await get_hide_cost(session)
    unlimited = _is_unlimited(message.from_user.id)

    if not unlimited and user.points < cost:
        await message.answer(
            low_credit_text(user.points, cost),
            reply_markup=_credit_keyboard(),
        )
        return

    await state.set_state(HideFlow.waiting_for_sessionid)
    await message.answer(instruction_text(cost, user.points, unlimited))


@router.message(HideFlow.waiting_for_sessionid, F.text)
async def handle_sessionid(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    await state.clear()
    if message.from_user is None:
        return

    sessionid = (message.text or "").strip()

    try:
        await message.delete()
    except Exception:
        pass

    processing = await message.answer("⌛ Working…")

    user, _ = await register_user(session, message.from_user)
    cost = await get_hide_cost(session)
    unlimited = _is_unlimited(message.from_user.id)

    async def refund() -> None:
        if cost <= 0:
            return
        await session.execute(
            update(User)
            .where(User.user_id == user.user_id)
            .values(points=User.points + cost)
        )
        await session.commit()
        await session.refresh(user)

    if not unlimited and cost > 0:
        reserved = await session.execute(
            update(User)
            .where(User.user_id == user.user_id, User.points >= cost)
            .values(points=User.points - cost)
        )
        if reserved.rowcount != 1:
            await session.rollback()
            await processing.edit_text(
                low_credit_text(user.points, cost),
                reply_markup=_credit_keyboard(),
            )
            return
        await session.commit()
        await session.refresh(user)

    try:
        body = await asyncio.to_thread(hide_lists, sessionid)
    except ValueError as exc:
        await refund()
        await processing.edit_text(f"❌ Bad input: {esc(exc)}")
        return
    except RuntimeError as exc:
        await refund()
        await processing.edit_text(f"❌ {esc(exc)}")
        return
    except Exception as exc:
        logger.exception("Unexpected hide_lists error")
        await refund()
        await processing.edit_text(f"❌ Unexpected error: {type(exc).__name__}")
        return

    data = body.get("data") if isinstance(body, dict) else None
    root = "xdt_api__v1__settings__set_bool"
    matches = (
        [
            value
            for key, value in data.items()
            if (key == root or key.startswith(root + "(")) and isinstance(value, dict)
        ]
        if isinstance(data, dict)
        else []
    )
    result = matches[0] if len(matches) == 1 else {}

    if (
        not isinstance(body, dict)
        or body.get("errors")
        or body.get("error")
        or body.get("status") == "fail"
        or result.get("value") is not True
        or any(
            result.get(key)
            for key in (
                "error_name_value",
                "errorNameValue",
                "fallback_message",
                "fallbackMessage",
            )
        )
    ):
        await refund()
        await processing.edit_text("❌ Failed. Your sessionid may be expired or invalid.")
        return

    user.total_success += 1

    credited: tuple[int, int] | None = None
    if not user.referral_credited and user.referred_by:
        referrer = await session.get(User, user.referred_by)
        if referrer is not None:
            points = await get_referral_points(session)
            referrer.points += points
            credited = (referrer.user_id, points)
        user.referral_credited = True

    await session.commit()
    await session.refresh(user)

    if credited is not None:
        await safe_send(
            bot,
            credited[0],
            "🎉 <b>Referral reward!</b>\n\n"
            f"A friend you invited completed their first hide. You earned "
            f"<b>{credited[1]} {_token_word(credited[1])}</b>.\n\n"
            "Use /hide to hide an account or /redeem to claim a reward.",
        )

    if unlimited:
        spent = "💵 Cost: free (admin)\n"
        balance_line = "⭐ Tokens left: ♾ Unlimited (admin)"
    else:
        spent = f"💵 Spent: {cost} {_token_word(cost)}\n" if cost > 0 else ""
        balance_line = f"⭐ Tokens left: <b>{user.points}</b>"
    await processing.edit_text(
        "✅ <b>Done!</b>\n\n"
        f"Instagram user ID: <code>{esc(instagram_user_id(sessionid))}</code>\n\n"
        "Your following and followers are now hidden.\n"
        "🔐 For safety, change your Instagram password.\n\n"
        f"{spent}"
        f"{balance_line}"
    )
