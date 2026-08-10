"""Invitations, on the wire."""

from __future__ import annotations

from pydantic import BaseModel

from .groups import Player


class Invitation(BaseModel):
    """A token and the player it is for. The link is built by whoever shows it."""

    token: str
    player: Player


class RedeemRequest(BaseModel):
    token: str
