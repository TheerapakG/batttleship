from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ..shared import models


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "player"

    id: Mapped[UUID] = mapped_column(primary_key=True, nullable=False, default=uuid4)
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    rating: Mapped[int] = mapped_column(nullable=False, default=1200)
    coins: Mapped[int] = mapped_column(nullable=False, default=1000000)
    admin: Mapped[bool] = mapped_column(nullable=False, default=False)
    auth_token: Mapped[UUID] = mapped_column(
        unique=True, nullable=False, index=True, default=uuid4
    )
    transfer_code: Mapped[Optional[str]] = mapped_column(String(24), index=True)
    ships: Mapped[list["Ship"]] = relationship()
    emotes: Mapped[list["Emote"]] = relationship()

    def _to_shared(self):
        return models.Player(
            self.id,
            self.name,
            self.rating,
            self.admin,
            self.auth_token,
            self.transfer_code,
            self.coins,
            [s.variant_id for s in self.ships],
            [e.variant_id for e in self.emotes],
        )

    async def to_shared(self, db_session: AsyncSession):
        return await db_session.run_sync(lambda _: self._to_shared())


class Ship(Base):
    __tablename__ = "ship"

    id: Mapped[UUID] = mapped_column(primary_key=True, nullable=False, default=uuid4)
    variant_id: Mapped[UUID] = mapped_column(nullable=False)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey(Player.id), nullable=False)


class Emote(Base):
    __tablename__ = "emote"

    id: Mapped[UUID] = mapped_column(primary_key=True, nullable=False, default=uuid4)
    variant_id: Mapped[UUID] = mapped_column(nullable=False)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey(Player.id), nullable=False)


class FriendFrom(Base):
    __tablename__ = "friend_from"
    id: Mapped[UUID] = mapped_column(ForeignKey(Player.id), primary_key=True)
    friend_tos: Mapped[set["FriendAssociation"]] = relationship(
        back_populates="friend_from"
    )


class FriendTo(Base):
    __tablename__ = "friend_to"
    id: Mapped[UUID] = mapped_column(ForeignKey(Player.id), primary_key=True)
    friend_froms: Mapped[set["FriendAssociation"]] = relationship(
        back_populates="friend_to"
    )


class FriendAssociation(Base):
    __tablename__ = "friend_association"
    left_id: Mapped[UUID] = mapped_column(ForeignKey(FriendFrom.id), primary_key=True)
    right_id: Mapped[UUID] = mapped_column(ForeignKey(FriendTo.id), primary_key=True)
    verified: Mapped[bool] = mapped_column(nullable=False, default=False)
    friend_from: Mapped["FriendFrom"] = relationship(back_populates="friend_tos")
    friend_to: Mapped["FriendTo"] = relationship(back_populates="friend_froms")


async def create_dev_engine():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine
