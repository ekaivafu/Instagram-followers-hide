from __future__ import annotations

from urllib.parse import quote

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db import RedeemItem, Redemption, RequiredChat
from app.utils import short


def _builder() -> InlineKeyboardBuilder:
    return InlineKeyboardBuilder()


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = _builder()
    builder.button(text="🕵️ Hide Followers & Following", callback_data="hide:start")
    builder.button(text="👥 Refer & Earn", callback_data="menu:refer")
    builder.button(text="🎁 Redeem Rewards", callback_data="menu:redeem")
    builder.button(text="👤 My Profile", callback_data="menu:profile")
    builder.button(text="❓ Help", callback_data="menu:help")
    if is_admin:
        builder.button(text="🛠 Admin Panel", callback_data="adm:home")
    builder.adjust(1)
    return builder.as_markup()


def back_kb() -> InlineKeyboardMarkup:
    builder = _builder()
    builder.button(text="⬅️ Back", callback_data="menu:home")
    return builder.as_markup()


def join_kb(chats: list[RequiredChat]) -> InlineKeyboardMarkup:
    builder = _builder()
    for chat in chats:
        url = chat.invite_link or (f"https://t.me/{chat.username}" if chat.username else None)
        if url:
            builder.button(text=short(f"➡️ {chat.title}", 60), url=url)
    builder.button(text="✅ I've joined", callback_data="check_join")
    builder.adjust(1)
    return builder.as_markup()


def refer_kb(link: str) -> InlineKeyboardMarkup:
    share_text = "Hide your Instagram followers & following lists with this bot!"
    builder = _builder()
    builder.button(
        text="📤 Share with friends",
        url=f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(share_text, safe='')}",
    )
    builder.button(text="🔄 Refresh", callback_data="menu:refer")
    builder.button(text="⬅️ Back", callback_data="menu:home")
    builder.adjust(1)
    return builder.as_markup()


def low_credit_kb(support_username: str = "") -> InlineKeyboardMarkup:
    builder = _builder()
    builder.button(text="👥 Refer & Earn", callback_data="menu:refer")
    support = support_username.lstrip("@")
    if support:
        builder.button(text=f"💬 Contact @{support}", url=f"https://t.me/{support}")
    builder.button(text="⬅️ Back", callback_data="menu:home")
    builder.adjust(1)
    return builder.as_markup()


def redeem_list_kb(items: list[RedeemItem]) -> InlineKeyboardMarkup:
    builder = _builder()
    for item in items:
        builder.button(
            text=short(f"🎁 {item.title} — {item.cost} tokens", 60),
            callback_data=f"redeem:item:{item.id}",
        )
    builder.button(text="⬅️ Back", callback_data="menu:home")
    builder.adjust(1)
    return builder.as_markup()


def redeem_item_kb(item: RedeemItem) -> InlineKeyboardMarkup:
    builder = _builder()
    builder.button(
        text=short(f"✅ Redeem for {item.cost} tokens", 60),
        callback_data=f"redeem:buy:{item.id}",
    )
    builder.button(text="⬅️ Back to rewards", callback_data="menu:redeem")
    builder.adjust(1)
    return builder.as_markup()


def admin_home_kb() -> InlineKeyboardMarkup:
    builder = _builder()
    builder.button(text="📢 Required Chats", callback_data="adm:chats")
    builder.button(text="🎁 Redeem Items", callback_data="adm:redeem")
    builder.button(text="⚙️ Token Settings", callback_data="adm:referral")
    builder.button(text="🪙 Give Tokens", callback_data="adm:points")
    builder.button(text="⏳ Pending Redemptions", callback_data="adm:pending")
    builder.button(text="🔄 Refresh", callback_data="adm:home")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def admin_chats_kb(chats: list[RequiredChat]) -> InlineKeyboardMarkup:
    builder = _builder()
    for chat in chats:
        builder.button(
            text=short(f"🗑 {chat.title}", 60),
            callback_data=f"adm:chat:del:{chat.id}",
        )
    builder.button(text="➕ Add channel / group", callback_data="adm:chat:add")
    builder.button(text="⬅️ Back", callback_data="adm:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_items_kb(items: list[RedeemItem]) -> InlineKeyboardMarkup:
    builder = _builder()
    for item in items:
        status = "" if item.active else " (off)"
        builder.button(
            text=short(f"✏️ {item.title}{status}", 60),
            callback_data=f"adm:item:edit:{item.id}",
        )
    builder.button(text="➕ Add redeem item", callback_data="adm:item:add")
    builder.button(text="⬅️ Back", callback_data="adm:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_item_edit_kb(item: RedeemItem) -> InlineKeyboardMarkup:
    builder = _builder()
    builder.button(text="✏️ Title", callback_data=f"adm:item:field:{item.id}:title")
    builder.button(text="✏️ Description", callback_data=f"adm:item:field:{item.id}:description")
    builder.button(text="✏️ Cost", callback_data=f"adm:item:field:{item.id}:cost")
    builder.button(text="✏️ Stock", callback_data=f"adm:item:field:{item.id}:stock")
    builder.button(text="✏️ Reward text", callback_data=f"adm:item:field:{item.id}:reward")
    toggle = "🔴 Disable" if item.active else "🟢 Enable"
    builder.button(text=toggle, callback_data=f"adm:item:toggle:{item.id}")
    builder.button(text="🗑 Delete", callback_data=f"adm:item:del:{item.id}")
    builder.button(text="⬅️ Back", callback_data="adm:redeem")
    builder.adjust(2, 2, 1, 1, 1, 1)
    return builder.as_markup()


def admin_confirm_delete_kb(item_id: int) -> InlineKeyboardMarkup:
    builder = _builder()
    builder.button(text="🗑 Yes, delete", callback_data=f"adm:item:delok:{item_id}")
    builder.button(text="⬅️ Cancel", callback_data=f"adm:item:edit:{item_id}")
    builder.adjust(1)
    return builder.as_markup()


def admin_delivery_kb() -> InlineKeyboardMarkup:
    builder = _builder()
    builder.button(text="⚡ Automatic (code/text)", callback_data="adm:item:newdelivery:auto")
    builder.button(text="👤 Manual (admin delivers)", callback_data="adm:item:newdelivery:manual")
    builder.adjust(1)
    return builder.as_markup()


def admin_referral_kb() -> InlineKeyboardMarkup:
    builder = _builder()
    builder.button(text="✏️ Referral reward", callback_data="adm:referral:edit")
    builder.button(text="✏️ Hide cost", callback_data="adm:referral:cost")
    builder.button(text="✏️ Welcome bonus", callback_data="adm:referral:welcome")
    builder.button(text="⬅️ Back", callback_data="adm:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_token_kb(user_id: int) -> InlineKeyboardMarkup:
    builder = _builder()
    builder.button(text="➕ Add tokens", callback_data=f"adm:points:add:{user_id}")
    builder.button(text="✏️ Set exact balance", callback_data=f"adm:points:set:{user_id}")
    builder.button(text="⬅️ Back", callback_data="adm:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_pending_kb(redemptions: list[Redemption]) -> InlineKeyboardMarkup:
    builder = _builder()
    for redemption in redemptions:
        builder.button(
            text=short(f"✅ Complete #{redemption.id} — {redemption.item_title}", 60),
            callback_data=f"adm:fulfill:{redemption.id}",
        )
    builder.button(text="🔄 Refresh", callback_data="adm:pending")
    builder.button(text="⬅️ Back", callback_data="adm:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_back_kb(target: str = "adm:home") -> InlineKeyboardMarkup:
    builder = _builder()
    builder.button(text="⬅️ Back", callback_data=target)
    return builder.as_markup()


def pending_hint_kb() -> InlineKeyboardMarkup:
    builder = _builder()
    builder.button(text="⏳ View pending redemptions", callback_data="adm:pending")
    return builder.as_markup()
