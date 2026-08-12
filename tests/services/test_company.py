"""Who you have played with, who against, and how it went.

The standings know a player won five matches. They do not know who was on the other end of
them, and no table records it — it has to be counted off the matches. That count is easy to
get subtly wrong in ways nothing else would notice: reading the score from the wrong side of
the net, counting a partner as an opponent, or scoring a draw as a win for both.

In an Americano every pair partners exactly once by construction, so these numbers only start
saying something across a season. In a Mexicano they are the season — the whole format is
"the table decides who you play with next", and after eight rounds it has an opinion about who
carries you.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from conftest import NAMES, make_club
from padel_tour.engine import Format, TournamentConfig
from padel_tour.services import advance_round, record_score, start_tournament
from padel_tour.services.stats import player_stats

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.services import TournamentView

TARGET = 24


async def played_out(session: AsyncSession) -> tuple[TournamentView, tuple[uuid.UUID, ...]]:
    """One eight-player Americano, every round scored 14:10 to the first pair."""
    club = await make_club(session)
    view = await start_tournament(
        session,
        club.group_id,
        list(club.players),
        TournamentConfig(Format.AMERICANO, points_per_match=TARGET),
        seed=11,
        actor=club.owner,
    )
    for number in range(1, view.total_rounds + 1):
        for match in view.rounds[number - 1].matches:
            view = await record_score(
                session,
                view.id,
                round_no=number,
                court=match.court,
                score_a=14,
                score_b=10,
                actor=club.owner,
            )
    return view, club.players


async def test_an_americano_partners_everybody_exactly_once(session: AsyncSession) -> None:
    """The design guarantee, read back out of the results.

    Worth checking here rather than only in the engine: if this counted partners wrongly it
    would still produce a plausible-looking list, and the whist schedule is the one case
    where the right answer is known in advance for every single pair.
    """
    _, players = await played_out(session)

    stats = await player_stats(session, players[0])

    assert len(stats.partners) == len(NAMES) - 1
    assert {line.played for line in stats.partners} == {1}


async def test_every_opponent_is_met_exactly_twice(session: AsyncSession) -> None:
    """The other half of the whist design, and the one an off-by-one would break."""
    _, players = await played_out(session)

    stats = await player_stats(session, players[0])

    assert {line.played for line in stats.opponents} == {2}


async def test_a_partner_is_not_also_counted_as_an_opponent(session: AsyncSession) -> None:
    """Same match, two lists, and the totals have to add up separately."""
    _, players = await played_out(session)

    stats = await player_stats(session, players[0])

    assert sum(line.played for line in stats.partners) == stats.matches
    assert sum(line.played for line in stats.opponents) == stats.matches * 2


async def test_wins_are_read_from_the_right_side_of_the_net(session: AsyncSession) -> None:
    """Every match went 14:10 to the first pair, so wins and losses must mirror exactly.

    Reading the score from the wrong side would give a player who lost everything a perfect
    record, and the totals would still look sane.
    """
    _, players = await played_out(session)

    for player_id in players:
        stats = await player_stats(session, player_id)

        assert sum(line.won for line in stats.partners) == stats.wins
        # Each of my wins is a loss for two opponents, so what they won against me is what I
        # did not win — counted twice over, once per person on their side.
        assert sum(line.won for line in stats.opponents) == stats.wins * 2


async def test_a_draw_is_a_win_for_nobody(session: AsyncSession) -> None:
    """It happened, so it counts as played; calling it half a win would make the rate lie."""
    club = await make_club(session)
    view = await start_tournament(
        session,
        club.group_id,
        list(club.players),
        TournamentConfig(Format.MEXICANO, points_per_match=TARGET, rounds=1),
        seed=11,
        actor=club.owner,
    )
    for match in view.rounds[0].matches:
        view = await record_score(
            session,
            view.id,
            round_no=1,
            court=match.court,
            score_a=12,
            score_b=12,
            actor=club.owner,
        )

    stats = await player_stats(session, club.players[0])

    assert [line.played for line in stats.partners] == [1]
    assert [line.won for line in stats.partners] == [0]
    assert {line.won for line in stats.opponents} == {0}


async def test_the_order_is_most_played_first(session: AsyncSession) -> None:
    """So "who do I play with most" is the top of the list rather than a sort in the client."""
    _, players = await played_out(session)

    stats = await player_stats(session, players[0])
    counts = [line.played for line in stats.opponents]

    assert counts == sorted(counts, reverse=True)


async def test_a_rate_travels_with_its_count(session: AsyncSession) -> None:
    """One match won together is 100%, and a screen showing only that would be lying."""
    _, players = await played_out(session)

    stats = await player_stats(session, players[0])
    partner = stats.partners[0]

    assert partner.win_rate in (0.0, 1.0)
    assert partner.played == 1


async def test_somebody_who_has_played_nothing_has_no_company(session: AsyncSession) -> None:
    club = await make_club(session)

    stats = await player_stats(session, club.players[0])

    assert stats.partners == ()
    assert stats.opponents == ()


async def test_a_mexicano_repeats_partners_and_the_count_shows_it(
    session: AsyncSession,
) -> None:
    """The case the feature is actually for.

    Mexicano redraws every round from the table, so over enough rounds some pairs recur and
    others never meet. An Americano cannot show this — its schedule forbids it.
    """
    club = await make_club(session)
    view = await start_tournament(
        session,
        club.group_id,
        list(club.players),
        TournamentConfig(Format.MEXICANO, points_per_match=TARGET, rounds=8),
        seed=7,
        actor=club.owner,
    )
    for number in range(1, 9):
        for match in view.rounds[number - 1].matches:
            view = await record_score(
                session,
                view.id,
                round_no=number,
                court=match.court,
                score_a=14,
                score_b=10,
                actor=club.owner,
            )
        if number < 8:
            view = await advance_round(session, view.id, actor=club.owner)

    stats = await player_stats(session, club.players[0])

    assert stats.matches == 8
    assert max(line.played for line in stats.partners) > 1, (
        "eight Mexicano rounds among eight players must repeat at least one pairing"
    )
