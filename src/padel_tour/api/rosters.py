"""Starting a group and keeping its roster.

Small on purpose. A group made here gets an owner — unlike one made from a Telegram chat,
where the chat is already the membership list and there is nobody to single out. On the web
there is no chat to answer that question, so whoever creates the group answers it.

Running tournaments from the browser is the next milestone; this is the part without which
signing in leads nowhere.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from padel_tour.services import add_player, create_group, list_players
from padel_tour.services.groups import get_group

from .deps import API_PREFIX, RequiredAccount, Session
from .schemas import Group, GroupDetail, Player

router = APIRouter(prefix=API_PREFIX, tags=["roster"])

MAX_NAME = 80


class NewGroup(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME)


class NewPlayer(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME)


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def make_group(body: NewGroup, session: Session, actor: RequiredAccount) -> Group:
    """Start a group. You own it."""
    return Group.of(await create_group(session, body.name, owner_account_id=actor.id))


@router.post("/groups/{group_id}/players", status_code=status.HTTP_201_CREATED)
async def make_player(
    group_id: uuid.UUID, body: NewPlayer, session: Session, actor: RequiredAccount
) -> GroupDetail:
    """Put somebody on the roster. Owners only.

    Answers with the whole roster rather than the one player: the screen that made this call
    is showing the roster, and one round trip beats two.
    """
    await add_player(session, group_id, body.name, actor=actor)
    group = await get_group(session, group_id)
    roster = await list_players(session, group_id)
    return GroupDetail(
        id=group.id,
        name=group.name,
        players=[Player.of(player) for player in roster],
        is_owner=True,
    )


__all__ = ["router"]
