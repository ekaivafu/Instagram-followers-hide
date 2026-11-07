from __future__ import annotations

from aiogram.types import User as TelegramUser
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import context
from app.db import User, get_welcome_tokens


async def register_user(
    session: AsyncSession,
    telegram_user: TelegramUser,
    referral_id: int | None = None,
) -> tuple[User, bool]:
    user = await session.get(User, telegram_user.id)
    created = user is None
    if created:
        user = User(user_id=telegram_user.id)
        user.points = max(0, await get_welcome_tokens(session))
        session.add(user)

    user.username = telegram_user.username
    user.first_name = telegram_user.first_name

    if created and referral_id and referral_id != telegram_user.id:
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
