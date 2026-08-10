"""Groups and the people in them, on the wire."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from padel_tour.services import GroupView, PlayerView

#: Long enough for a full name, short enough that nobody pastes an essay into a chip.
MAX_NAME = 80


class Group(BaseModel):
    id: uuid.UUID
    name: str
    player_count: int

    @classmethod
    def of(cls, view: GroupView) -> Group:
        return cls(id=view.id, name=view.name, player_count=view.player_count)


class Player(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool

    @classmethod
    def of(cls, view: PlayerView) -> Player:
        return cls(id=view.id, name=view.name, is_active=view.is_active)


class GroupDetail(BaseModel):
    id: uuid.UUID
    name: str
    players: list[Player]
    is_owner: bool = Field(
        default=False,
        description="Whether the caller keeps this roster. Hides controls that would 403.",
    )


class NewGroup(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME)


class NewPlayer(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME)


class RenamedPlayer(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME)
