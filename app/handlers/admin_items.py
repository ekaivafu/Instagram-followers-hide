from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import RedeemItem
from app.filters import IsAdmin
from app.keyboards import (
    admin_back_kb,
    admin_confirm_delete_kb,
    admin_delivery_kb,
    admin_item_edit_kb,
    admin_items_kb,
)
from app.states import AdminFlow
from app.utils import esc, safe_edit, short, stock_label

router = Router(name="admin_items")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def _as_int(text: str) -> int | None:
    try:
        return int(text.strip())
    except (TypeError, ValueError):
        return None


def render_item(item: RedeemItem) -> str:
    if item.description:
        description = esc(item.description)
    else:
        description = "No description."
    reward = esc(short(item.reward_text, 300)) if item.reward_text else "—"
    delivery = "Automatic" if item.delivery_type == "auto" else "Manual"
    return (
        f"🎁 <b>{esc(item.title)}</b>\n\n"
        f"{description}\n\n"
        f"💵 Cost: <b>{item.cost} points</b>\n"
        f"📦 Stock: {stock_label(item.stock)}\n"
        f"🚚 Delivery: {delivery}\n"
        f"📢 Status: {'Active' if item.active else 'Disabled'}\n\n"
        f"<b>Reward text</b>\n{reward}"
    )


async def items_view(session: AsyncSession) -> tuple[str, list[RedeemItem]]:
    items = list(
        (await session.scalars(select(RedeemItem).order_by(RedeemItem.cost, RedeemItem.id))).all()
    )
    lines = ["🎁 <b>Redeem Items</b>", ""]
    if not items:
        lines.append("No redeem items yet. Add your first reward.")
    else:
        for item in items:
            status = "active" if item.active else "disabled"
            delivery = "auto" if item.delivery_type == "auto" else "manual"
            lines.append(
                f"• <b>{esc(item.title)}</b> — {item.cost} pts\n"
                f"  stock: {stock_label(item.stock)} · {delivery} · {status}"
            )
    return "\n".join(lines), items


async def create_item(session: AsyncSession, data: dict) -> RedeemItem:
    item = RedeemItem(
        title=data["title"],
        description=data.get("description", ""),
        cost=int(data["cost"]),
        stock=int(data["stock"]),
        delivery_type=data.get("delivery_type", "manual"),
        reward_text=data.get("reward_text", ""),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.callback_query(F.data == "adm:redeem")
async def adm_items(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    text, items = await items_view(session)
    await safe_edit(callback.message, text, admin_items_kb(items))


@router.callback_query(F.data == "adm:item:add")
async def adm_item_add(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(AdminFlow.item_title)
    if callback.message is not None:
        await safe_edit(
            callback.message,
            "➕ <b>Add redeem item</b>\n\nSend the item title (e.g. "
            "<i>Instagram followers pack</i>).\n\nSend /cancel to abort.",
            admin_back_kb("adm:redeem"),
        )


@router.message(AdminFlow.item_title, F.text)
async def item_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("❌ Title cannot be empty.")
        return
    if len(title) > 128:
        await message.answer("❌ Title must be 128 characters or fewer.")
        return
    await state.update_data(title=title)
    await state.set_state(AdminFlow.item_description)
    await message.answer(
        "📝 Send a description for this reward, or send <code>-</code> to skip."
    )


@router.message(AdminFlow.item_description, F.text)
async def item_description(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) > 1000:
        await message.answer("❌ Description must be 1000 characters or fewer.")
        return
    await state.update_data(description="" if text == "-" else text)
    await state.set_state(AdminFlow.item_cost)
    await message.answer("💵 Send the cost in points (whole number, 1 or more).")


@router.message(AdminFlow.item_cost, F.text)
async def item_cost(message: Message, state: FSMContext) -> None:
    cost = _as_int(message.text or "")
    if cost is None or cost < 1 or cost > 100_000_000:
        await message.answer("❌ Send a whole number between 1 and 100,000,000.")
        return
    await state.update_data(cost=cost)
    await state.set_state(AdminFlow.item_stock)
    await message.answer(
        "📦 Send the stock amount.\n\n"
        "<code>-1</code> = unlimited\n<code>0</code> = out of stock"
    )


@router.message(AdminFlow.item_stock, F.text)
async def item_stock(message: Message, state: FSMContext) -> None:
    stock = _as_int(message.text or "")
    if stock is None or stock < -1 or stock > 100_000_000:
        await message.answer("❌ Send -1 for unlimited, or a whole number 0 or more.")
        return
    await state.update_data(stock=stock)
    await state.set_state(AdminFlow.item_delivery)
    await message.answer(
        "🚚 How should this reward be delivered?",
        reply_markup=admin_delivery_kb(),
    )


@router.callback_query(AdminFlow.item_delivery, F.data.startswith("adm:item:newdelivery:"))
async def item_delivery(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()
    delivery = (callback.data or "").rsplit(":", 1)[-1]
    await state.update_data(delivery_type=delivery)

    if delivery == "auto":
        await state.set_state(AdminFlow.item_reward)
        if callback.message is not None:
            await safe_edit(
                callback.message,
                "⚡ Send the reward text or code that will be sent to the user "
                "immediately after redeeming.\n\nSend <code>-</code> to leave it empty.",
                admin_back_kb("adm:redeem"),
            )
        return

    data = await state.get_data()
    item = await create_item(session, data)
    await state.clear()
    if callback.message is not None:
        await safe_edit(
            callback.message,
            f"✅ Item created.\n\n{render_item(item)}",
            admin_item_edit_kb(item),
        )


@router.message(AdminFlow.item_reward, F.text)
async def item_reward(message: Message, state: FSMContext, session: AsyncSession) -> None:
    text = (message.text or "").strip()
    if len(text) > 3000:
        await message.answer("❌ Reward text must be 3000 characters or fewer.")
        return
    await state.update_data(reward_text="" if text == "-" else text)
    data = await state.get_data()
    item = await create_item(session, data)
    await state.clear()
    await message.answer(
        f"✅ Item created.\n\n{render_item(item)}",
        reply_markup=admin_item_edit_kb(item),
    )


@router.callback_query(F.data.startswith("adm:item:edit:"))
async def item_edit(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    try:
        item_id = int((callback.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return
    item = await session.get(RedeemItem, item_id)
    if item is None:
        text, items = await items_view(session)
        await safe_edit(callback.message, "❌ Item not found.\n\n" + text, admin_items_kb(items))
        return
    await safe_edit(callback.message, render_item(item), admin_item_edit_kb(item))


@router.callback_query(F.data.startswith("adm:item:field:"))
async def item_field(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        return
    try:
        item_id = int(parts[3])
    except ValueError:
        return
    field = parts[4]
    labels = {
        "title": "title",
        "description": "description",
        "cost": "cost in points",
        "stock": "stock amount (-1 for unlimited)",
        "reward": "reward text or code",
    }
    if field not in labels:
        return

    await state.clear()
    await state.set_state(AdminFlow.edit_value)
    await state.update_data(item_id=item_id, field=field)
    if callback.message is not None:
        await safe_edit(
            callback.message,
            f"✏️ Send the new {labels[field]}.\n\n"
            "For description or reward text, send <code>-</code> to clear it.\n\n"
            "Send /cancel to abort.",
            admin_back_kb(f"adm:item:edit:{item_id}"),
        )


@router.message(AdminFlow.edit_value, F.text)
async def item_edit_value(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    item_id = data.get("item_id")
    field = data.get("field")
    item = await session.get(RedeemItem, int(item_id)) if item_id else None
    if item is None or not field:
        await state.clear()
        await message.answer("❌ Item no longer exists.", reply_markup=admin_back_kb("adm:redeem"))
        return

    text = (message.text or "").strip()

    if field == "title":
        if not text or len(text) > 128:
            await message.answer("❌ Title must be between 1 and 128 characters.")
            return
        item.title = text
    elif field == "description":
        if len(text) > 1000:
            await message.answer("❌ Description must be 1000 characters or fewer.")
            return
        item.description = "" if text == "-" else text
    elif field == "cost":
        value = _as_int(text)
        if value is None or value < 1:
            await message.answer("❌ Cost must be a whole number of 1 or more.")
            return
        item.cost = value
    elif field == "stock":
        value = _as_int(text)
        if value is None or value < -1:
            await message.answer("❌ Stock must be -1 (unlimited) or 0 or more.")
            return
        item.stock = value
    elif field == "reward":
        if len(text) > 3000:
            await message.answer("❌ Reward text must be 3000 characters or fewer.")
            return
        item.reward_text = "" if text == "-" else text
    else:
        await state.clear()
        await message.answer("❌ Unknown field.")
        return

    await session.commit()
    await state.clear()
    await message.answer(
        f"✅ Updated <b>{esc(field)}</b>.\n\n{render_item(item)}",
        reply_markup=admin_item_edit_kb(item),
    )


@router.callback_query(F.data.startswith("adm:item:toggle:"))
async def item_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    if callback.message is None:
        return
    try:
        item_id = int((callback.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return
    item = await session.get(RedeemItem, item_id)
    if item is None:
        return
    item.active = not item.active
    await session.commit()
    state = "enabled" if item.active else "disabled"
    await safe_edit(
        callback.message,
        f"✅ Item {state}.\n\n{render_item(item)}",
        admin_item_edit_kb(item),
    )


@router.callback_query(F.data.startswith("adm:item:del:"))
async def item_delete_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    if callback.message is None:
        return
    try:
        item_id = int((callback.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return
    item = await session.get(RedeemItem, item_id)
    if item is None:
        return
    await safe_edit(
        callback.message,
        f"🗑 Delete <b>{esc(item.title)}</b>?\n\n"
        "Past redemption history is kept, but this reward will disappear from the shop.",
        admin_confirm_delete_kb(item.id),
    )


@router.callback_query(F.data.startswith("adm:item:delok:"))
async def item_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    if callback.message is None:
        return
    try:
        item_id = int((callback.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return
    item = await session.get(RedeemItem, item_id)
    if item is None:
        return
    title = item.title
    await session.delete(item)
    await session.commit()
    text, items = await items_view(session)
    await safe_edit(
        callback.message,
        f"🗑 Deleted <b>{esc(title)}</b>.\n\n{text}",
        admin_items_kb(items),
    )
