"""Running a tournament: what the browser sends."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from padel_tour.engine import Format, PairingPattern, TournamentConfig

from .tournaments import MAX_ROUNDS


class NewTournament(BaseModel):
    player_ids: list[uuid.UUID] = Field(min_length=1)
    format: Format
    points_per_match: int = Field(default=24, ge=2)
    pairing_pattern: PairingPattern = PairingPattern.CROSSOVER
    rounds: int | None = Field(default=None, ge=1, le=MAX_ROUNDS)

    def config(self) -> TournamentConfig:
        """The engine's idea of the same thing.

        ``rounds`` is dropped for an Americano, which plays a fixed ``n - 1`` and refuses a
        round count outright. The screen keeps one form for both formats, so the field is
        filled in either way; ignoring it here matches how ``pairing_pattern`` already
        behaves for Americano and keeps the refusals for things the organiser can act on.
        """
        return TournamentConfig(
            format=self.format,
            points_per_match=self.points_per_match,
            pairing_pattern=self.pairing_pattern,
            rounds=None if self.format is Format.AMERICANO else self.rounds,
        )


class NewScore(BaseModel):
    score_a: int = Field(ge=0)
    score_b: int = Field(ge=0)
