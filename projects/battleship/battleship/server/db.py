from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..shared import models


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "player"

    id: Mapped[UUID] = mapped_column(primary_key=True, nullable=False, default=uuid4)
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    rating: Mapped[int] = mapped_column(nullable=False, default=1200)
    admin: Mapped[bool] = mapped_column(nullable=False, default=False)
    auth_token: Mapped[UUID] = mapped_column(
        unique=True, nullable=False, index=True, default=uuid4
    )
    transfer_code: Mapped[Optional[str]] = mapped_column(String(24), index=True)

    def to_shared(self):
        return models.Player(
            self.id,
            self.name,
            self.rating,
            self.admin,
            self.auth_token,
            self.transfer_code,
        )


async def create_dev_engine():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine
