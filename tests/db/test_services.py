"""Service layer, exercised against a real database rather than mocks.

A mocked repository would only prove we called what we called. What matters here is whether
the data actually lands right, which only a real database can answer.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from conftest import EIGHT_NAMES, americano_config, mexicano_config
from padel_tour.db import PROVIDER_TELEGRAM
from padel_tour.engine import (
    Format,
    InvalidScoreError,
    PairingPattern,
    RerollTooLateError,
    RoundIncompleteError,
)
from padel_tour.services import (
    ActiveTournamentExistsError,
    DuplicateGroupNameError,
    DuplicatePlayerNameError,
    GroupNotFoundError,
    InactivePlayerError,
    PlayerNotInGroupError,
    TournamentNotFoundError,
    active_tournament,
    add_player,
    advance_round,
    amend_score,
    create_group,
    deactivate_player,
    finish_tournament,
    get_tournament,
    group_for_link,
    link_group,
    list_groups,
    list_players,
    list_tournaments,
    player_history,
    record_score,
    rename_player,
    reroll_tournament,
    start_tournament,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.services import TournamentView


async def play_round(session: AsyncSession, view: TournamentView, number: int) -> TournamentView:
    """Score every court of one round, 14:10 each."""
    rnd = view.rounds[number - 1]
    for match in rnd.matches:
        view = await record_score(
            session,
            view.id,
            round_no=number,
            court=match.court,
            score_a=14,
            score_b=10,
        )
    return view


# --------------------------------------------------------------------------- groups


async def test_create_and_list_groups(session: AsyncSession) -> None:
    await create_group(session, "Tuesday")
    await create_group(session, "Thursday")
    names = [group.name for group in await list_groups(session)]
    assert names == ["Thursday", "Tuesday"]


async def test_group_names_must_differ(session: AsyncSession) -> None:
    await create_group(session, "Tuesday")
    with pytest.raises(DuplicateGroupNameError):
        await create_group(session, "Tuesday")


async def test_group_name_is_trimmed(session: AsyncSession) -> None:
    group = await create_group(session, "  Tuesday  ")
    assert group.name == "Tuesday"


async def test_a_group_is_findable_through_its_link(session: AsyncSession) -> None:
    """The bot reaches a group by chat id; the service layer only sees a provider."""
    created = await create_group(session, "Tuesday")
    await link_group(session, created.id, PROVIDER_TELEGRAM, "-100500")

    found = await group_for_link(session, PROVIDER_TELEGRAM, "-100500")
    assert found is not None
    assert found.id == created.id
    assert await group_for_link(session, PROVIDER_TELEGRAM, "-1") is None


async def test_unknown_group_is_reported(session: AsyncSession) -> None:
    with pytest.raises(GroupNotFoundError):
        await list_players(session, uuid.uuid7())


# --------------------------------------------------------------------------- players


@pytest.mark.usefixtures("eight_players")
async def test_players_are_listed_by_name(session: AsyncSession, group_id: uuid.UUID) -> None:
    assert [p.name for p in await list_players(session, group_id)] == sorted(EIGHT_NAMES)


async def test_duplicate_player_name_is_refused(session: AsyncSession, group_id: uuid.UUID) -> None:
    await add_player(session, group_id, "Ann")
    with pytest.raises(DuplicatePlayerNameError):
        await add_player(session, group_id, "Ann")


async def test_readding_a_retired_player_brings_them_back(
    session: AsyncSession, group_id: uuid.UUID
) -> None:
    """'Add Ann' when Ann used to play here obviously means welcome her back."""
    ann = await add_player(session, group_id, "Ann")
    await deactivate_player(session, ann.id)

    again = await add_player(session, group_id, "Ann")
    assert again.id == ann.id
    assert again.is_active


async def test_deactivated_players_are_hidden_but_not_gone(
    session: AsyncSession, group_id: uuid.UUID
) -> None:
    ann = await add_player(session, group_id, "Ann")
    await deactivate_player(session, ann.id)

    assert await list_players(session, group_id) == []
    assert len(await list_players(session, group_id, include_inactive=True)) == 1


async def test_renaming_refuses_a_taken_name(session: AsyncSession, group_id: uuid.UUID) -> None:
    await add_player(session, group_id, "Ann")
    ben = await add_player(session, group_id, "Ben")
    with pytest.raises(DuplicatePlayerNameError):
        await rename_player(session, ben.id, "Ann")


# --------------------------------------------------------------------------- lifecycle


async def test_starting_an_americano_draws_the_whole_schedule(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, americano_config())

    assert view.total_rounds == 7
    assert len(view.rounds) == 7
    assert all(len(rnd.matches) == 2 for rnd in view.rounds)
    assert len(view.standings) == 8


async def test_a_mexicano_starts_with_one_round(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, mexicano_config())
    assert view.total_rounds == 4
    assert len(view.rounds) == 1


async def test_views_carry_names_not_ids(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, americano_config())
    playing = {name for match in view.rounds[0].matches for name in (*match.team_a, *match.team_b)}
    assert playing <= set(EIGHT_NAMES)
    assert {row.name for row in view.standings} == set(EIGHT_NAMES)


async def test_a_group_runs_one_tournament_at_a_time(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    await start_tournament(session, group_id, eight_players, americano_config())
    with pytest.raises(ActiveTournamentExistsError):
        await start_tournament(session, group_id, eight_players, americano_config())


async def test_finishing_frees_the_group_for_the_next_tournament(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    first = await start_tournament(session, group_id, eight_players, americano_config())
    await finish_tournament(session, first.id)

    assert await active_tournament(session, group_id) is None
    second = await start_tournament(session, group_id, eight_players, americano_config())
    assert second.id != first.id


async def test_finishing_stamps_the_time(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, americano_config())
    assert view.finished_at is None
    done = await finish_tournament(session, view.id)
    assert done.finished
    assert done.finished_at is not None


async def test_outsiders_cannot_be_entered(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    other = await create_group(session, "Thursday")
    stranger = await add_player(session, other.id, "Zoe")

    with pytest.raises(PlayerNotInGroupError):
        await start_tournament(
            session, group_id, [*eight_players[:7], stranger.id], americano_config()
        )


async def test_retired_players_cannot_be_entered(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    await deactivate_player(session, eight_players[0])
    with pytest.raises(InactivePlayerError):
        await start_tournament(session, group_id, eight_players, americano_config())


async def test_unknown_tournament_is_reported(session: AsyncSession) -> None:
    with pytest.raises(TournamentNotFoundError):
        await get_tournament(session, uuid.uuid7())


# --------------------------------------------------------------------------- scoring


async def test_recording_a_score_updates_the_table(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, americano_config())
    winners = view.rounds[0].matches[0].team_a

    view = await record_score(session, view.id, round_no=1, court=1, score_a=14, score_b=10)

    scored = {row.name: row.points_for for row in view.standings}
    assert scored[winners[0]] == 14
    assert scored[winners[1]] == 14


async def test_a_bad_score_is_refused_by_the_engine(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, americano_config())
    with pytest.raises(InvalidScoreError):
        await record_score(session, view.id, round_no=1, court=1, score_a=15, score_b=10)


async def test_amending_a_score_recomputes_everything(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, americano_config())
    view = await record_score(session, view.id, round_no=1, court=1, score_a=24, score_b=0)
    winner = view.rounds[0].matches[0].team_a[0]
    assert {row.name: row.points_for for row in view.standings}[winner] == 24

    view = await amend_score(session, view.id, round_no=1, court=1, score_a=13, score_b=11)
    assert {row.name: row.points_for for row in view.standings}[winner] == 13


async def test_the_last_score_finishes_the_tournament(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, americano_config())
    for number in range(1, 8):
        view = await play_round(session, view, number)

    assert view.finished
    assert view.finished_at is not None
    assert await active_tournament(session, group_id) is None


# --------------------------------------------------------------------------- mexicano


async def test_advancing_needs_a_complete_round(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, mexicano_config())
    await record_score(session, view.id, round_no=1, court=1, score_a=14, score_b=10)
    with pytest.raises(RoundIncompleteError):
        await advance_round(session, view.id)


async def test_each_mexicano_round_is_stored_as_it_is_drawn(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, mexicano_config(rounds=3))

    for number in range(1, 4):
        assert len(view.rounds) == number
        view = await play_round(session, view, number)
        if number < 3:
            view = await advance_round(session, view.id)

    # Still open: a Mexicano's round count is the organiser's plan, and reaching it is not
    # the same as being done. Ending it is a decision somebody makes.
    assert not view.finished
    assert len((await get_tournament(session, view.id)).rounds) == 3

    view = await finish_tournament(session, view.id)
    assert view.finished


async def test_mexicano_pairs_the_leaders_together(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(
        session, group_id, eight_players, mexicano_config(pattern=PairingPattern.CROSSOVER)
    )
    view = await play_round(session, view, 1)
    top_four = {row.name for row in view.standings[:4]}

    view = await advance_round(session, view.id)
    court_one = view.rounds[1].matches[0]
    assert {*court_one.team_a, *court_one.team_b} == top_four


# --------------------------------------------------------------------------- reroll


async def test_reroll_changes_the_draw(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, americano_config(), seed=1)
    before = [(m.team_a, m.team_b) for rnd in view.rounds for m in rnd.matches]

    view = await reroll_tournament(session, view.id, seed=2)
    after = [(m.team_a, m.team_b) for rnd in view.rounds for m in rnd.matches]

    assert before != after
    assert len(view.rounds) == 7


async def test_reroll_is_refused_once_play_has_started(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, americano_config())
    await record_score(session, view.id, round_no=1, court=1, score_a=14, score_b=10)
    with pytest.raises(RerollTooLateError):
        await reroll_tournament(session, view.id)


# --------------------------------------------------------------------------- history


async def test_the_archive_names_the_winner(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, mexicano_config(rounds=1))
    view = await play_round(session, view, 1)

    summaries = await list_tournaments(session, group_id)
    assert len(summaries) == 1
    assert summaries[0].winner_name == view.standings[0].name
    assert summaries[0].player_count == 8
    assert summaries[0].rounds_played == 1


async def test_an_unplayed_tournament_has_no_winner(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    await start_tournament(session, group_id, eight_players, americano_config())
    assert (await list_tournaments(session, group_id))[0].winner_name is None


async def test_player_history_follows_the_player(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(session, group_id, eight_players, americano_config())
    await finish_tournament(session, view.id)

    assert len(await player_history(session, eight_players[0])) == 1
    lonely = await add_player(session, group_id, "Ivan")
    assert await player_history(session, lonely.id) == []


async def test_renaming_a_player_updates_old_tournaments(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    """Tournaments store ids, so a new name shows up everywhere at once."""
    view = await start_tournament(session, group_id, eight_players, americano_config())
    assert "Ann" in {row.name for row in view.standings}

    await rename_player(session, eight_players[0], "Anna")

    reloaded = await get_tournament(session, view.id)
    names = {row.name for row in reloaded.standings}
    assert "Anna" in names
    assert "Ann" not in names


async def test_format_survives_the_round_trip(
    session: AsyncSession, group_id: uuid.UUID, eight_players: list[uuid.UUID]
) -> None:
    view = await start_tournament(
        session, group_id, eight_players, mexicano_config(pattern=PairingPattern.SPLIT)
    )
    reloaded = await get_tournament(session, view.id)
    assert reloaded.format is Format.MEXICANO
    assert reloaded.pairing_pattern is PairingPattern.SPLIT
