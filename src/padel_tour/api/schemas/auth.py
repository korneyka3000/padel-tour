"""Signing in, on the wire."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr

from .groups import Group


class MagicLinkRequest(BaseModel):
    email: EmailStr


class LaunchRequest(BaseModel):
    """The opaque string Telegram hands a Mini App. Never trusted before it is verified."""

    init_data: str


class EnterRequest(BaseModel):
    token: str


class Accepted(BaseModel):
    """Answered whether or not the address is known — see the endpoint for why."""

    status: str = "sent"


class Me(BaseModel):
    id: uuid.UUID
    display_name: str | None
    groups: list[Group]
