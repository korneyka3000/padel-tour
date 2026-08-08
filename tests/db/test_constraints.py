"""The database has to refuse bad data on its own.

These go around the service layer on purpose. Services check the same things and give nicer
errors, but a check in application code is only as good as everyone remembering to call it —
these tests prove the last line of defence actually holds.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from padel_tour.db import Group, Match, Player, Round, Tournament, TournamentPlayer
from padel_tour.engine import Format, PairingPattern

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def make_tournament(session: AsyncSession, group_id: uuid.UUID) -> Tournament:
    row = Tournament(
        group_id=group_id,
        format=Format.AMERICANO,
        points_per_match=24,
        pairing_pattern=PairingPattern.CROSSOVER,
        total_rounds=7,
        seed=1,
    )
    session.add(row)
    await session.flush()
    return row


async def make_round(session: AsyncSession, tournament_id: uuid.UUID, number: int) -> Round:
    row = Round(tournament_id=tournament_id, number=number)
    session.add(row)
    await session.flush()
    return row


def make_match(round_id: uuid.UUID, court: int, **scores: int | None) -> Match:
    return Match(
        round_id=round_id,
        court=court,
        team_a1=uuid.uuid7(),
        team_a2=uuid.uuid7(),
        team_b1=uuid.uuid7(),
        team_b2=uuid.uuid7(),
        **scores,
    )


async def test_group_names_are_unique(session: AsyncSession) -> None:
    session.add(Group(name="Tuesday"))
    await session.flush()
    session.add(Group(name="Tuesday"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_player_names_are_unique_within_a_group(
    session: AsyncSession, group_id: uuid.UUID
) -> None:
    session.add(Player(group_id=group_id, name="Ann"))
    await session.flush()
    session.add(Player(group_id=group_id, name="Ann"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_the_same_name_is_fine_in_another_group(session: AsyncSession) -> None:
    """Two groups can each have an Ann — they are different people."""
    first, second = Group(name="Tuesday"), Group(name="Thursday")
    session.add_all([first, second])
    await session.flush()

    session.add_all(
        [
            Player(group_id=first.id, name="Ann"),
            Player(group_id=second.id, name="Ann"),
        ]
    )
    await session.flush()


async def test_round_numbers_are_unique_within_a_tournament(
    session: AsyncSession, group_id: uuid.UUID
) -> None:
    tournament = await make_tournament(session, group_id)
    await make_round(session, tournament.id, 1)
    session.add(Round(tournament_id=tournament.id, number=1))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_one_match_per_court_per_round(session: AsyncSession, group_id: uuid.UUID) -> None:
    tournament = await make_tournament(session, group_id)
    rnd = await make_round(session, tournament.id, 1)
    session.add(make_match(rnd.id, court=1))
    await session.flush()
    session.add(make_match(rnd.id, court=1))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_draw_positions_are_unique(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    """The draw position is the last tie-break, so a duplicate would make ranking ambiguous."""
    tournament = await make_tournament(session, group_id)
    session.add_all(
        [
            TournamentPlayer(
                tournament_id=tournament.id, player_id=eight_players[0], draw_position=0
            ),
            TournamentPlayer(
                tournament_id=tournament.id, player_id=eight_players[1], draw_position=0
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.parametrize(
    "scores",
    [
        {"score_a": 14, "score_b": None},
        {"score_a": None, "score_b": 10},
    ],
)
async def test_half_a_score_is_impossible(
    session: AsyncSession, group_id: uuid.UUID, scores: dict[str, int | None]
) -> None:
    tournament = await make_tournament(session, group_id)
    rnd = await make_round(session, tournament.id, 1)
    session.add(make_match(rnd.id, court=1, **scores))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_negative_scores_are_rejected(session: AsyncSession, group_id: uuid.UUID) -> None:
    tournament = await make_tournament(session, group_id)
    rnd = await make_round(session, tournament.id, 1)
    session.add(make_match(rnd.id, court=1, score_a=-1, score_b=25))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_an_unplayed_match_may_have_no_score(
    session: AsyncSession, group_id: uuid.UUID
) -> None:
    tournament = await make_tournament(session, group_id)
    rnd = await make_round(session, tournament.id, 1)
    match = make_match(rnd.id, court=1)
    session.add(match)
    await session.flush()
    assert not match.played
