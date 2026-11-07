"""End-to-end checks for referral crediting on join.

Run with:

    python tests/referral_flow_check.py

It uses a temporary SQLite database and a fake bot, so it never touches
Telegram or the production database.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ADMIN_IDS", "")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram.types import User as TelegramUser  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.db import Base, Redemption  # noqa: E402
from app.services import (  # noqa: E402
    credit_referral_if_due,
    referral_counts,
    register_user,
)

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(message)
    PASSED += 1
    print(f"  ok - {message}")


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **_: object) -> None:
        self.sent.append((chat_id, text))


def tg(user_id: int, first_name: str) -> TelegramUser:
    return TelegramUser(id=user_id, is_bot=False, first_name=first_name)


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="insta-referral-")) / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    bot = FakeBot()

    # --- Referrer and a new invited user ---------------------------------
    async with sessions() as session:
        referrer, _ = await register_user(session, tg(100, "Alice"))
        invited, created = await register_user(session, tg(200, "Bob"), referral_id=100)

        check(created, "invited user is registered as new")
        check(invited.referred_by == 100, "invited user keeps the referrer id")

        earned = await credit_referral_if_due(bot, session, invited)
        await session.refresh(referrer)
        await session.refresh(invited)

        check(earned == 1, "referrer earns the configured reward")
        check(referrer.points == 2, "referrer balance grows by one token")
        check(invited.referral_credited, "invited user is marked as credited")
        check(len(bot.sent) == 1, "referrer receives exactly one notification")
        chat_id, text = bot.sent[0]
        check(chat_id == 100, "notification is sent to the referrer")
        check("Bob" in text, "notification includes the friend's name")
        check("<b>2</b>" in text, "notification includes the new balance")

        # --- No double credit --------------------------------------------
        again = await credit_referral_if_due(bot, session, invited)
        await session.refresh(referrer)
        check(again is None, "second crediting attempt is a no-op")
        check(referrer.points == 2, "balance is not increased twice")
        check(len(bot.sent) == 1, "no duplicate notification is sent")

    # --- Self-referral is blocked ----------------------------------------
    async with sessions() as session:
        self_user, _ = await register_user(session, tg(300, "Mallory"), referral_id=300)
        check(self_user.referred_by is None, "self-referral is never recorded")
        earned = await credit_referral_if_due(bot, session, self_user)
        await session.refresh(self_user)
        check(earned is None, "self-referral pays nothing")
        check(self_user.points == 1, "self-referral keeps only the welcome bonus")

    # --- Existing active user cannot be retroactively claimed ------------
    async with sessions() as session:
        active, _ = await register_user(session, tg(400, "Carol"))
        active.total_success = 1
        await session.commit()

        claimed, _ = await register_user(session, tg(400, "Carol"), referral_id=100)
        check(claimed.referred_by is None, "user with a completed hide is not claimable")

    # --- Existing unused user can still be claimed (reported test case) --
    async with sessions() as session:
        fresh, _ = await register_user(session, tg(500, "Dave"))
        claimed, _ = await register_user(session, tg(500, "Dave"), referral_id=100)
        check(claimed.referred_by == 100, "unused existing account can be claimed once")

        earned = await credit_referral_if_due(bot, session, claimed)
        await session.refresh(claimed)
        check(earned == 1, "claiming an unused existing account credits the referrer")
        check(claimed.referral_credited, "the claim is marked as credited")

    # --- User who already redeemed a reward cannot be claimed ------------
    async with sessions() as session:
        redeemer, _ = await register_user(session, tg(550, "Frank"))
        redeemer.points = 0
        session.add(Redemption(user_id=550, item_title="Test reward", cost=1, status="completed"))
        await session.commit()

        claimed, _ = await register_user(session, tg(550, "Frank"), referral_id=100)
        check(claimed.referred_by is None, "user who redeemed a reward is not claimable")

    # --- Missing referrer is cleaned up safely ---------------------------
    async with sessions() as session:
        orphan, _ = await register_user(session, tg(600, "Eve"))
        orphan.referred_by = 999999
        await session.commit()

        earned = await credit_referral_if_due(bot, session, orphan)
        await session.refresh(orphan)
        check(earned is None, "missing referrer pays nothing")
        check(orphan.referred_by is None, "invalid referrer is removed")
        check(orphan.referral_credited, "invalid referral is not retried forever")

    # --- Referral counters ------------------------------------------------
    async with sessions() as session:
        total, credited = await referral_counts(session, 100)
        check(total == 2, "two friends are linked to the referrer")
        check(credited == 2, "both linked friends are credited")

    await engine.dispose()
    print(f"\nAll {PASSED} checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
