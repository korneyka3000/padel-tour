"""Groups and the people in them, on the wire."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from padel_tour.services import GroupView, PlayerView

#: Long enough for a full name, short enough that nobody pastes an essay into a chip.
MAX_NAME = 80


#: The service layer's model, used as it is — see :class:`~padel_tour.services.GroupView`.
#: The one field a client must not see is excluded there rather than dropped by a copy here.
Group = GroupView


#: The service layer's model, used as it is.
#:
#: It was copied field for field into a second class that differed only by leaving out
#: ``group_id`` — which is no secret: it is in the URL of most requests that return a
#: player. A duplicate that hides nothing only gets a chance to disagree.
Player = PlayerView


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
