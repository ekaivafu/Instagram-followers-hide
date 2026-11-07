from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import User as TelegramUser
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import context
from app.config import settings
from app.db import Redemption, User, get_referral_points, get_welcome_tokens
from app.utils import esc, safe_send

logger = logging.getLogger(__name__)


async def register_user(
    session: AsyncSession,
    telegram_user: TelegramUser,
    referral_id: int | None = None,
) -> tuple[User, bool]:
    welcome = max(0, await get_welcome_tokens(session))

    user = await session.get(User, telegram_user.id)
    created = user is None
    if created:
        user = User(user_id=telegram_user.id)
        user.points = welcome
        session.add(user)

    user.username = telegram_user.username
    user.first_name = telegram_user.first_name

    # Only unattributed, unused accounts can be claimed by a referral link.
    # This also blocks a user from referring their own Telegram account.
    if (
        referral_id
        and referral_id != telegram_user.id
        and user.referred_by is None
        and not user.referral_credited
        and (user.total_success or 0) == 0
        and user.points <= welcome
    ):
        has_redemption = bool(
            await session.scalar(
                select(func.count())
                .select_from(Redemption)
                .where(Redemption.user_id == user.user_id)
            )
        )
        if not has_redemption:
            referrer = await session.get(User, referral_id)
            if referrer is not None:
                user.referred_by = referral_id

    await session.commit()
    return user, created


def referral_link(user_id: int) -> str:
    username = context.bot_username or "your_bot"
    return f"https://t.me/{username}?start=ref_{user_id}"


async def referral_counts(session: AsyncSession, user_id: int) -> tuple[int, int]:
    total = await session.scalar(
        select(func.count()).select_from(User).where(User.referred_by == user_id)
    )
    credited = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.referred_by == user_id, User.referral_credited.is_(True))
    )
    return int(total or 0), int(credited or 0)


def _display_name(user: User) -> str:
    if user.first_name:
        return user.first_name
    if user.username:
        return f"@{user.username}"
    return "A friend"


async def credit_referral_if_due(
    bot: Bot,
    session: AsyncSession,
    user: User,
) -> int | None:
    """Credit the referrer as soon as the invited user joins the bot.

    Safe to call on every interaction:
    * ``users.referral_credited`` makes the payout happen at most once.
    * A user can never be credited for referring their own account.
    * The reward is added to the referrer atomically, then the referrer is
      notified with the friend's name and their new balance.
    """
    if user.referral_credited or not user.referred_by:
        return None

    if user.referred_by == user.user_id:
        # Defensive: never let a user reward themselves.
        user.referred_by = None
        user.referral_credited = True
        await session.commit()
        return None

    referrer = await session.get(User, user.referred_by)
    if referrer is None:
        user.referred_by = None
        user.referral_credited = True
        await session.commit()
        return None

    # Atomic claim so concurrent updates cannot pay the same referral twice.
    claimed = await session.execute(
        update(User)
        .where(User.user_id == user.user_id, User.referral_credited.is_(False))
        .values(referral_credited=True)
    )
    if claimed.rowcount != 1:
        await session.commit()
        return None

    points = await get_referral_points(session)
    if points > 0:
        await session.execute(
            update(User)
            .where(User.user_id == referrer.user_id)
            .values(points=User.points + points)
        )
    await session.commit()
    await session.refresh(user)
    await session.refresh(referrer)

    token_word = "token" if points == 1 else "tokens"
    balance = (
        "♾ Unlimited (admin)"
        if referrer.user_id in settings.admin_ids
        else f"<b>{referrer.points}</b>"
    )
    text = (
        "🎉 <b>Referral reward!</b>\n\n"
        f"Your friend <b>{esc(_display_name(user))}</b> joined the bot using "
        "your referral link.\n"
        f"🎁 You earned <b>{points} {token_word}</b>.\n"
        f"⭐ Your tokens: {balance}\n\n"
        "Use /hide to hide an account or /redeem to claim a reward."
    )
    if not await safe_send(bot, referrer.user_id, text):
        logger.info("Referrer %s could not be notified", referrer.user_id)
    return points
