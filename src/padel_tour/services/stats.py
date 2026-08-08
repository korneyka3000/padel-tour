"""Statistics across tournaments.

Everything here is derived, never stored: the tournaments are the record, and a summary is
just a question asked of them. That keeps the numbers honest when a score is corrected after
the fact — nothing needs invalidating because nothing was cached.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from padel_tour.db import Tournament, TournamentPlayer
from padel_tour.db.mapper import load_state, to_player_id
from padel_tour.engine import standings

from .groups import get_player

# Runtime import: the dataclass annotation below is resolved when the class is built.
from .views import TournamentSummary  # noqa: TC001

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

#: A finish in the top three counts as a podium.
PODIUM_RANK = 3


@dataclass(frozen=True, slots=True)
class PlayerStats:
    """One player's record across everything they have played."""

    player_id: uuid.UUID
    name: str
    tournaments: int
    matches: int
    wins: int
    draws: int
    losses: int
    points_for: int
    points_against: int
    best_rank: int | None
    podiums: int
    history: tuple[TournamentSummary, ...]

    @property
    def average_points(self) -> float:
        """Points per match — the only fair comparison when people play different amounts."""
        return round(self.points_for / self.matches, 1) if self.matches else 0.0

    @property
    def win_rate(self) -> float:
        return round(self.wins / self.matches, 3) if self.matches else 0.0


async def player_stats(session: AsyncSession, player_id: uuid.UUID) -> PlayerStats:
    """Summarise a player by replaying every tournament they took part in.

    Only tournaments with at least one result count towards a rank: finishing "first" in a
    tournament nobody played is not an achievement.
    """
    from .tournaments import _loaded, _names, _to_summary  # noqa: PLC0415 - avoids a cycle

    player = await get_player(session, player_id)
    engine_id = to_player_id(player_id)

    rows = await session.scalars(
        select(Tournament)
        .join(TournamentPlayer, TournamentPlayer.tournament_id == Tournament.id)
        .where(TournamentPlayer.player_id == player_id)
        .order_by(Tournament.created_at.desc())
        .options(*_loaded())
    )

    history: list[TournamentSummary] = []
    matches = wins = draws = losses = 0
    points_for = points_against = 0
    ranks: list[int] = []

    for row in rows:
        history.append(_to_summary(row))
        state = load_state(row)
        if engine_id not in _names(row):
            continue

        line = next(row_ for row_ in standings(state) if row_.player == engine_id)
        matches += line.played
        wins += line.wins
        draws += line.draws
        losses += line.losses
        points_for += line.points_for
        points_against += line.points_against
        if line.played:
            ranks.append(line.rank)

    return PlayerStats(
        player_id=player_id,
        name=player.name,
        tournaments=len(history),
        matches=matches,
        wins=wins,
        draws=draws,
        losses=losses,
        points_for=points_for,
        points_against=points_against,
        best_rank=min(ranks) if ranks else None,
        podiums=sum(1 for rank in ranks if rank <= PODIUM_RANK),
        history=tuple(history),
    )
