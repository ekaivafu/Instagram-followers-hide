from aiogram.fsm.state import State, StatesGroup


class HideFlow(StatesGroup):
    waiting_for_sessionid = State()


class AdminFlow(StatesGroup):
    chat = State()
    referral_points = State()
    hide_cost = State()
    welcome_tokens = State()
    points_user_id = State()
    points_value = State()
    points_add_value = State()
    item_title = State()
    item_description = State()
    item_cost = State()
    item_stock = State()
    item_delivery = State()
    item_reward = State()
    edit_value = State()
