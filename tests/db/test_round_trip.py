"""The point of this milestone: a tournament survives the process that created it.

Each test commits, throws away the session and every object it held, opens a fresh one, and
checks that what comes back is what went in. Reading through the same session would prove
nothing — the identity map would hand back the very objects we just wrote.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from conftest import americano_config, mexicano_config
from padel_tour.engine import Format, PairingPattern, TournamentConfig, standings
from padel_tour.services import (
    active_tournament,
    add_player,
    advance_round,
    create_group,
    finish_tournament,
    get_tournament,
    list_tournaments,
    record_score,
    start_tournament,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from padel_tour.services import TournamentView


def fingerprint(view: TournamentView) -> dict[str, object]:
    """Everything about a tournament that must survive a reload, in comparable form."""
    return {
        "format": view.format,
        "points": view.points_per_match,
        "pattern": view.pairing_pattern,
        "total_rounds": view.total_rounds,
        "finished": view.finished,
        "rounds": [
            (
                rnd.number,
                [(m.court, m.team_a, m.team_b, m.score_a, m.score_b) for m in rnd.matches],
            )
            for rnd in view.rounds
        ],
        "standings": [
            (row.rank, row.name, row.points_for, row.points_against, row.wins)
            for row in view.standings
        ],
        "progression": {
            str(player): [(p.round_no, p.points_for, p.cumulative_points, p.rank) for p in points]
            for player, points in sorted(view.progression.items(), key=lambda kv: str(kv[0]))
        },
    }


async def seed_group(session: AsyncSession, size: int = 8) -> tuple[uuid.UUID, list[uuid.UUID]]:
    group = await create_group(session, "Tuesday Padel")
    names = [f"Player {index:02d}" for index in range(1, size + 1)]
    players = [(await add_player(session, group.id, name)).id for name in names]
    return group.id, players


@pytest.mark.parametrize(
    ("config_factory", "rounds_to_play"),
    [
        (americano_config, 3),
        (lambda: mexicano_config(rounds=3), 2),
    ],
    ids=["americano", "mexicano"],
)
async def test_a_partly_played_tournament_reloads_identically(
    factory: async_sessionmaker[AsyncSession],
    config_factory: Callable[[], TournamentConfig],
    rounds_to_play: int,
) -> None:
    async with factory() as session:
        group_id, players = await seed_group(session)
        view = await start_tournament(session, group_id, players, config_factory(), seed=4242)
        for number in range(1, rounds_to_play + 1):
            for match in view.rounds[number - 1].matches:
                view = await record_score(
                    session,
                    view.id,
                    round_no=number,
                    court=match.court,
                    score_a=13 + match.court,
                    score_b=11 - match.court,
                )
            if view.format is Format.MEXICANO and number < rounds_to_play:
                view = await advance_round(session, view.id)
        expected = fingerprint(view)
        tournament_id = view.id
        await session.commit()

    async with factory() as session:
        reloaded = await get_tournament(session, tournament_id)
        assert fingerprint(reloaded) == expected


async def test_play_resumes_after_a_reload(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """The real scenario: stop mid-tournament, come back, keep going."""
    async with factory() as session:
        group_id, players = await seed_group(session)
        view = await start_tournament(session, group_id, players, americano_config())
        view = await record_score(session, view.id, round_no=1, court=1, score_a=14, score_b=10)
        tournament_id = view.id
        await session.commit()

    async with factory() as session:
        resumed = await active_tournament(session, group_id)
        assert resumed is not None
        assert resumed.id == tournament_id

        pending = resumed.next_unfinished_round
        assert pending is not None
        assert pending.number == 1  # court 2 is still outstanding

        resumed = await record_score(
            session, tournament_id, round_no=1, court=2, score_a=20, score_b=4
        )
        assert resumed.rounds[0].complete
        assert resumed.next_unfinished_round is not None
        assert resumed.next_unfinished_round.number == 2
        await session.commit()

    async with factory() as session:
        final = await get_tournament(session, tournament_id)
        assert sum(row.points_for for row in final.standings) == 2 * 24 * 2


async def test_a_finished_tournament_stays_finished(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        group_id, players = await seed_group(session)
        view = await start_tournament(session, group_id, players, americano_config())
        view = await finish_tournament(session, view.id)
        tournament_id = view.id
        stamped = view.finished_at
        await session.commit()

    async with factory() as session:
        reloaded = await get_tournament(session, tournament_id)
        assert reloaded.finished
        assert reloaded.finished_at == stamped
        assert await active_tournament(session, group_id) is None


async def test_the_engine_agrees_with_itself_across_a_reload(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Standings recomputed from stored rows must match the live ones exactly."""
    async with factory() as session:
        group_id, players = await seed_group(session)
        view = await start_tournament(
            session, group_id, players, mexicano_config(rounds=2), seed=77
        )
        for match in view.rounds[0].matches:
            view = await record_score(
                session, view.id, round_no=1, court=match.court, score_a=15, score_b=9
            )
        live = standings(view.state)
        tournament_id = view.id
        await session.commit()

    async with factory() as session:
        reloaded = await get_tournament(session, tournament_id)
        assert standings(reloaded.state) == live


async def test_the_seed_is_stored_so_the_draw_can_be_replayed(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        group_id, players = await seed_group(session)
        view = await start_tournament(session, group_id, players, americano_config(), seed=1234)
        tournament_id = view.id
        await session.commit()

    async with factory() as session:
        reloaded = await get_tournament(session, tournament_id)
        assert reloaded.state.seed == 1234
        assert reloaded.state.draw_order == view.state.draw_order


async def test_the_archive_survives_a_reload(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        group_id, players = await seed_group(session)
        for _ in range(2):
            view = await start_tournament(session, group_id, players, mexicano_config(rounds=1))
            for match in view.rounds[0].matches:
                await record_score(
                    session, view.id, round_no=1, court=match.court, score_a=14, score_b=10
                )
            # A Mexicano no longer ends itself, and a group cannot start a second tournament
            # while one is still open — so ending it is part of playing one now.
            await finish_tournament(session, view.id)
        await session.commit()

    async with factory() as session:
        archive = await list_tournaments(session, group_id)
        assert len(archive) == 2
        assert all(entry.finished for entry in archive)
        assert all(entry.winner_name for entry in archive)
        assert archive[0].created_at >= archive[1].created_at


async def test_a_twelve_player_americano_reloads_whole(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Eleven rounds and three courts — the largest thing we expect in practice."""
    async with factory() as session:
        group_id, players = await seed_group(session, size=12)
        view = await start_tournament(session, group_id, players, americano_config())
        tournament_id = view.id
        expected = fingerprint(view)
        await session.commit()

    async with factory() as session:
        reloaded = await get_tournament(session, tournament_id)
        assert len(reloaded.rounds) == 11
        assert all(len(rnd.matches) == 3 for rnd in reloaded.rounds)
        assert fingerprint(reloaded) == expected


async def test_pairing_pattern_survives_and_still_drives_the_draw(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """A reloaded Mexicano must draw its next round the same way the original would."""
    async with factory() as session:
        group_id, players = await seed_group(session)
        view = await start_tournament(
            session,
            group_id,
            players,
            mexicano_config(rounds=3, pattern=PairingPattern.SPLIT),
            seed=9,
        )
        for match in view.rounds[0].matches:
            view = await record_score(
                session, view.id, round_no=1, court=match.court, score_a=16, score_b=8
            )
        ranked = [row.name for row in view.standings]
        tournament_id = view.id
        await session.commit()

    async with factory() as session:
        advanced = await advance_round(session, tournament_id)
        court_one = advanced.rounds[1].matches[0]
        # split is 1+3 against 2+4
        assert set(court_one.team_a) == {ranked[0], ranked[2]}
        assert set(court_one.team_b) == {ranked[1], ranked[3]}
