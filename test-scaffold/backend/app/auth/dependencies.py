from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models.user import User


async def get_current_user(db: AsyncSession = Depends(get_db)) -> User:
    """Stub auth dependency -- replace with real authentication."""
    raise NotImplementedError("Replace with your authentication logic")
