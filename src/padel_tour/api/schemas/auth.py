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
    #: Whether this account is listed as an administrator, by either door.
    #:
    #: The fact, not the list. A screen needs it to decide whether to offer the admin
    #: section at all — an entry that leads to a wall of refusals is worse than no entry.
    is_admin: bool = False
