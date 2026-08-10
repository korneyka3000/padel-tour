"""One player's record across everything they have played."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from .tournaments import TournamentCard


class PlayerProfile(BaseModel):
    """A player's record across every tournament they have played."""

    id: uuid.UUID
    name: str
    tournaments: int
    matches: int
    wins: int
    points_for: int
    average_points: float = Field(description="Points per match played")
    best_rank: int | None
    podiums: int
    history: list[TournamentCard]
