"""Statistics across tournaments.

Everything here is derived, never stored: the tournaments are the record, and a summary is
just a question asked of them. That keeps the numbers honest when a score is corrected after
the fact — nothing needs invalidating because nothing was cached.
"""

from __future__ import annotations

import uuid  # noqa: TC003 - Pydantic resolves annotations when the class is built
from typing import TYPE_CHECKING

from pydantic import Field, computed_field

from padel_tour import repositories
from padel_tour.db.mapper import load_state, to_player_id, to_uuid
from padel_tour.engine import standings

from .groups import get_player

# Runtime imports: Pydantic resolves the annotations below when the class is built.
from .views import Together, TournamentSummary, View

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Tournament

#: A finish in the top three counts as a podium.
PODIUM_RANK = 3


class PlayerStats(View):
    """One player's record across everything they have played — and the JSON of it.

    Serialised as ``id`` rather than ``player_id`` because that is what the profile endpoint
    has always answered and a client is reading it. The field keeps the longer name in
    process, where "which id" is a real question.
    """

    player_id: uuid.UUID = Field(serialization_alias="id")
    name: str
    tournaments: int
    matches: int
    wins: int
    points_for: int
    best_rank: int | None
    podiums: int
    history: tuple[TournamentSummary, ...]

    #: Everyone this player has partnered, most-played first.
    partners: tuple[Together, ...] = ()
    #: Everyone they have played against, most-played first.
    opponents: tuple[Together, ...] = ()

    #: Counted, and not yet shown anywhere. Kept off the wire until a screen wants them,
    #: rather than shipped on the chance that one might.
    draws: int = Field(default=0, exclude=True)
    losses: int = Field(default=0, exclude=True)
    points_against: int = Field(default=0, exclude=True)

    @computed_field(description="Points per match played")
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
    from .tournaments import _names, _to_summary  # noqa: PLC0415 - avoids a cycle

    player = await get_player(session, player_id)
    engine_id = to_player_id(player_id)

    rows = await repositories.tournaments_of_player(session, player_id)

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

    with_them, against_them = _company(rows, engine_id)

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
        partners=with_them,
        opponents=against_them,
    )


def _company(
    rows: Sequence[Tournament], me: str
) -> tuple[tuple[Together, ...], tuple[Together, ...]]:
    """Who this player has played with and against, and how it went.

    Counted from the matches themselves rather than from any table, because no table records
    it: the standings know a player won five, not who was on the other end of them. In an
    Americano everybody partners everybody exactly once by construction, so these numbers are
    interesting mainly across a season; in a Mexicano they are the season.

    A draw counts for neither side. It happened, so it is in ``played``, and calling it half a
    win would make a rate that means something different from the one next to it.
    """
    from .tournaments import _names  # noqa: PLC0415 - avoids a cycle

    partners: dict[str, list[int]] = {}
    opponents: dict[str, list[int]] = {}
    names: dict[str, str] = {}

    for row in rows:
        names.update(_names(row))
        for rnd in load_state(row).rounds:
            for match in rnd.matches:
                if match.result is None:
                    continue
                mine, theirs = match.team_a, match.team_b
                if me in (theirs.a, theirs.b):
                    mine, theirs = theirs, mine
                elif me not in (mine.a, mine.b):
                    continue

                ours = match.result.score_a if mine is match.team_a else match.result.score_b
                yours = match.result.score_b if mine is match.team_a else match.result.score_a
                won = int(ours > yours)

                partner = mine.b if mine.a == me else mine.a
                partners.setdefault(partner, []).append(won)
                for rival in (theirs.a, theirs.b):
                    opponents.setdefault(rival, []).append(won)

    return _ranked(partners, names), _ranked(opponents, names)


def _ranked(counted: dict[str, list[int]], names: dict[str, str]) -> tuple[Together, ...]:
    """Most-played first, and ties broken by name so the order never wobbles."""
    return tuple(
        sorted(
            (
                Together(
                    player_id=to_uuid(player),
                    name=names.get(player, player),
                    played=len(results),
                    won=sum(results),
                )
                for player, results in counted.items()
            ),
            key=lambda line: (-line.played, line.name),
        )
    )
