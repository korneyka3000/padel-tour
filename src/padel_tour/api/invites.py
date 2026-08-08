"""Becoming a player.

Signing in says a person is stable; it says nothing about which name on which roster they
are. An invitation is the only thing that joins the two, and it is issued against one
player, which is what makes claiming somebody else's history impossible.

The same token works here and in the bot. The link invites someone to a *player*, not to
a surface.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from padel_tour.services import create_invite, peek_invite, redeem_invite

from .deps import API_PREFIX, RequiredAccount, Session
from .schemas import Player

router = APIRouter(prefix=API_PREFIX, tags=["invites"])


class Invitation(BaseModel):
    """What the owner hands over. The token is shown once and never stored in the clear."""

    token: str
    player: Player


class RedeemRequest(BaseModel):
    token: str


@router.post("/players/{player_id}/invite")
async def issue_invite(
    player_id: uuid.UUID, session: Session, actor: RequiredAccount
) -> Invitation:
    """Invite somebody to be this player. Owners only."""
    token = await create_invite(session, actor, player_id)
    return Invitation(token=token, player=Player.of(await peek_invite(session, token)))


@router.get("/invites/{token}")
async def read_invite(token: str, session: Session) -> Player:
    """Who an invitation is for, without accepting it.

    Open on purpose: the page has to be able to say "join as Аня" before it asks anyone to
    sign in. Knowing the token is already the whole of the secret.
    """
    return Player.of(await peek_invite(session, token))


@router.post("/invites/redeem")
async def accept_invite(body: RedeemRequest, session: Session, actor: RequiredAccount) -> Player:
    """Accept an invitation as the signed-in account."""
    return Player.of(await redeem_invite(session, body.token, actor))


__all__ = ["router"]
