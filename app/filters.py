from aiogram.filters import BaseFilter

from app.config import settings


class IsAdmin(BaseFilter):
    async def __call__(self, event) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and user.id in settings.admin_ids
