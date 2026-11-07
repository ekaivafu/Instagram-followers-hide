from aiogram.exceptions import TelegramAPIError, TelegramNetworkError

# aiogram exposes TelegramAPIError / TelegramNetworkError instead of a single base class.
TelegramError = (TelegramAPIError, TelegramNetworkError)
