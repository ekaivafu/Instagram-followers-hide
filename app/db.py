from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    referred_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    referral_credited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    total_success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class RequiredChat(Base):
    __tablename__ = "required_chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invite_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="channel", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RedeemItem(Base):
    __tablename__ = "redeem_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cost: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=-1, nullable=False)
    delivery_type: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)
    reward_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Redemption(Base):
    __tablename__ = "redemptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_title: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    fulfilled_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _prepare_url(url: str) -> tuple[str, dict]:
    connect_args: dict = {}
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]

    if url.startswith("postgresql+asyncpg://"):
        parts = urlsplit(url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        ssl_modes = [value for key, value in query if key.lower() == "sslmode"]
        query = [(key, value) for key, value in query if key.lower() != "sslmode"]
        if any(mode in {"require", "verify-ca", "verify-full"} for mode in ssl_modes):
            connect_args["ssl"] = True
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    elif url.startswith("sqlite") and ":///" not in url:
        url = "sqlite+aiosqlite:///" + url

    return url, connect_args


def configure_database(database_url: str) -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    url, connect_args = _prepare_url(database_url)
    _engine = create_async_engine(url, connect_args=connect_args, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


async def init_db() -> None:
    if _engine is None:
        raise RuntimeError("Database is not configured. Call configure_database() first.")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_database() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    row = await session.get(Setting, key)
    return row.value if row else default


async def set_setting(session: AsyncSession, key: str, value: str | int) -> None:
    row = await session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=str(value)))
    else:
        row.value = str(value)
    await session.commit()


async def get_int_setting(session: AsyncSession, key: str, default: int) -> int:
    raw = await get_setting(session, key, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


async def get_referral_points(session: AsyncSession) -> int:
    return await get_int_setting(session, "referral_points", 1)


async def get_hide_cost(session: AsyncSession) -> int:
    return await get_int_setting(session, "hide_cost", 1)


async def get_welcome_tokens(session: AsyncSession) -> int:
    return await get_int_setting(session, "welcome_tokens", 1)
