import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _admin_ids(raw: str) -> tuple[int, ...]:
    values: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.add(int(part))
        except ValueError:
            raise RuntimeError(f"ADMIN_IDS contains a non-numeric value: {part!r}") from None
    return tuple(sorted(values))


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: tuple[int, ...]
    database_url: str
    webhook_url: str | None
    webhook_secret: str | None
    port: int
    support_username: str


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Create a .env file (see .env.example) or add the env var."
        )

    webhook_url = os.getenv("WEBHOOK_URL", "").strip() or None
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if not webhook_url and render_url:
        webhook_url = f"{render_url}/webhook"

    # Telegram only allows A-Z, a-z, 0-9, _ and - in secret tokens.
    raw_secret = os.getenv("WEBHOOK_SECRET", "").strip()
    webhook_secret = re.sub(r"[^A-Za-z0-9_-]", "", raw_secret)[:256] or None

    support = os.getenv("SUPPORT_USERNAME", "@tgekaiva").strip().lstrip("@")
    support_username = f"@{support}" if support else ""

    return Settings(
        bot_token=token,
        admin_ids=_admin_ids(os.getenv("ADMIN_IDS", "")),
        database_url=os.getenv("DATABASE_URL", "").strip() or "sqlite+aiosqlite:///./bot.db",
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
        port=int(os.getenv("PORT", "8080")),
        support_username=support_username,
    )


settings = load_settings()
