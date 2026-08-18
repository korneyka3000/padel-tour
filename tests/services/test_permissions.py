"""Who may do what.

These go through the service functions rather than calling the checks directly. A check
nobody calls protects nothing, and the whole reason permissions live in the service layer is
that the bot reaches those functions without passing through a route.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from conftest import account, claim, make_club
from padel_tour.db import PROVIDER_EMAIL, PROVIDER_TELEGRAM
from padel_tour.engine import Format, TournamentConfig
from padel_tour.services import (
    add_player,
    advance_round,
    ensure_identity,
    finish_tournament,
    groups_for_account,
    is_admin,
    is_member,
    record_score,
    require_member,
    reroll_tournament,
    start_tournament,
)
from padel_tour.services.errors import ForbiddenError, NotAMemberError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from conftest import Club
    from padel_tour.db import Account
    from padel_tour.services import TournamentView

AMERICANO = TournamentConfig(Format.AMERICANO, points_per_match=24)


async def a_tournament(session: AsyncSession, club: Club, organiser: Account) -> TournamentView:
    return await start_tournament(
        session, club.group_id, list(club.players), AMERICANO, actor=organiser, seed=7
    )


# ---------------------------------------------------------------------------- the roster


async def test_the_owner_keeps_the_roster(session: AsyncSession) -> None:
    club = await make_club(session)
    player = await add_player(session, club.group_id, "Костя", actor=club.owner)
    assert player.name == "Костя"


async def test_a_stranger_cannot_add_a_player(session: AsyncSession) -> None:
    club = await make_club(session)
    stranger = await account(session, "stranger@example.test")

    with pytest.raises(ForbiddenError):
        await add_player(session, club.group_id, "Костя", actor=stranger)


async def test_a_member_who_is_not_the_owner_cannot_add_a_player(session: AsyncSession) -> None:
    """Being on the roster and keeping the roster are different things."""
    club = await make_club(session)
    anya = await account(session, "anya@example.test")
    await claim(session, club.player("Аня"), anya)

    with pytest.raises(ForbiddenError):
        await add_player(session, club.group_id, "Костя", actor=anya)


async def test_a_group_nobody_owns_is_open(session: AsyncSession) -> None:
    """What a Telegram chat produces: the chat is the membership list."""
    club = await make_club(session, owned=False)
    passer_by = await account(session, "anyone@example.test")

    added = await add_player(session, club.group_id, "Костя", actor=passer_by)
    assert added.name == "Костя"


# ------------------------------------------------------------------------ running a game


async def test_a_stranger_cannot_start_a_tournament(session: AsyncSession) -> None:
    club = await make_club(session)
    stranger = await account(session, "stranger@example.test")

    with pytest.raises(ForbiddenError):
        await a_tournament(session, club, stranger)


async def test_whoever_starts_it_organises_it(session: AsyncSession) -> None:
    club = await make_club(session)
    anya = await account(session, "anya@example.test")
    await claim(session, club.player("Аня"), anya)

    view = await a_tournament(session, club, anya)
    assert view.organiser_account_id == anya.id


async def test_only_the_organiser_may_finish(session: AsyncSession) -> None:
    club = await make_club(session)
    anya = await account(session, "anya@example.test")
    borya = await account(session, "borya@example.test")
    await claim(session, club.player("Аня"), anya)
    await claim(session, club.player("Боря"), borya)
    view = await a_tournament(session, club, anya)

    with pytest.raises(ForbiddenError):
        await finish_tournament(session, view.id, actor=borya)

    finished = await finish_tournament(session, view.id, actor=anya)
    assert finished.finished


async def test_the_owner_can_take_over_a_tournament(session: AsyncSession) -> None:
    """The organiser goes home with the phone; the group is not stuck with a live screen."""
    club = await make_club(session)
    anya = await account(session, "anya@example.test")
    await claim(session, club.player("Аня"), anya)
    view = await a_tournament(session, club, anya)

    finished = await finish_tournament(session, view.id, actor=club.owner)
    assert finished.finished


async def test_a_tournament_with_no_organiser_is_open(session: AsyncSession) -> None:
    """Started from the CLI. Nobody recorded, so nobody is locked out."""
    club = await make_club(session, owned=False)
    view = await start_tournament(session, club.group_id, list(club.players), AMERICANO, seed=7)
    passer_by = await account(session, "anyone@example.test")

    finished = await finish_tournament(session, view.id, actor=passer_by)
    assert finished.finished


async def test_only_the_organiser_may_redraw(session: AsyncSession) -> None:
    club = await make_club(session)
    anya = await account(session, "anya@example.test")
    borya = await account(session, "borya@example.test")
    await claim(session, club.player("Аня"), anya)
    await claim(session, club.player("Боря"), borya)
    view = await a_tournament(session, club, anya)

    with pytest.raises(ForbiddenError):
        await reroll_tournament(session, view.id, actor=borya)


# ------------------------------------------------------------------------------- scoring


async def test_a_player_scores_their_own_match(session: AsyncSession) -> None:
    club = await make_club(session)
    anya = await account(session, "anya@example.test")
    await claim(session, club.player("Аня"), anya)
    view = await a_tournament(session, club, club.owner)

    court = next(
        match.court for match in view.rounds[0].matches if "Аня" in match.team_a + match.team_b
    )
    scored = await record_score(
        session, view.id, round_no=1, court=court, score_a=14, score_b=10, actor=anya
    )
    assert next(m for m in scored.rounds[0].matches if m.court == court).played


async def test_a_player_cannot_score_a_court_they_were_not_on(session: AsyncSession) -> None:
    """Two courts, and the wrong one is a real mis-tap — or a convenient mistake."""
    club = await make_club(session)
    anya = await account(session, "anya@example.test")
    await claim(session, club.player("Аня"), anya)
    view = await a_tournament(session, club, club.owner)

    elsewhere = next(
        match.court for match in view.rounds[0].matches if "Аня" not in match.team_a + match.team_b
    )

    with pytest.raises(ForbiddenError):
        await record_score(
            session, view.id, round_no=1, court=elsewhere, score_a=14, score_b=10, actor=anya
        )


async def test_an_unclaimed_member_may_still_score(session: AsyncSession) -> None:
    """Claiming a player is opt-in; before anyone has, the bot must still be usable."""
    club = await make_club(session, owned=False)
    view = await start_tournament(session, club.group_id, list(club.players), AMERICANO, seed=7)
    somebody = await account(session, "somebody@example.test")

    scored = await record_score(
        session, view.id, round_no=1, court=1, score_a=14, score_b=10, actor=somebody
    )
    assert scored.rounds[0].matches[0].played


async def test_a_stranger_cannot_score(session: AsyncSession) -> None:
    club = await make_club(session)
    view = await a_tournament(session, club, club.owner)
    stranger = await account(session, "stranger@example.test")

    with pytest.raises(ForbiddenError):
        await record_score(
            session, view.id, round_no=1, court=1, score_a=14, score_b=10, actor=stranger
        )


async def test_the_last_score_of_a_round_draws_the_next_one(session: AsyncSession) -> None:
    """Advancing follows from the standing, so it is not the organiser's to withhold."""
    club = await make_club(session)
    anya = await account(session, "anya@example.test")
    await claim(session, club.player("Аня"), anya)
    mexicano = TournamentConfig(Format.MEXICANO, points_per_match=24, rounds=3)
    view = await start_tournament(
        session, club.group_id, list(club.players), mexicano, actor=club.owner, seed=7
    )

    for match in view.rounds[0].matches:
        view = await record_score(
            session,
            view.id,
            round_no=1,
            court=match.court,
            score_a=14,
            score_b=10,
            actor=club.owner,
        )

    advanced = await advance_round(session, view.id, actor=anya)
    assert len(advanced.rounds) == 2


# --------------------------------------------------------------------------- admins


async def test_an_admin_is_not_stopped_by_membership(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A capability on the ordinary screens, rather than a second interface.

    Somebody fixing a group's tournament at eleven at night needs the screens that group
    uses, not a parallel set that would be missing whatever went wrong.
    """
    club = await make_club(session)
    outsider = await ensure_identity(session, PROVIDER_TELEGRAM, "999")
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "999")

    await require_member(session, outsider, club.group_id)


async def test_without_the_setting_nobody_is_an_admin(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The list lives in the deployment, so an empty one means the door is shut."""
    club = await make_club(session)
    outsider = await ensure_identity(session, PROVIDER_TELEGRAM, "999")
    monkeypatch.delenv("ADMIN_TELEGRAM_IDS", raising=False)

    with pytest.raises(NotAMemberError):
        await require_member(session, outsider, club.group_id)


async def test_an_admin_can_still_be_an_ordinary_player(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Being listed adds permission; it does not replace who somebody is."""
    club = await make_club(session)
    account = await ensure_identity(session, PROVIDER_TELEGRAM, "777")
    await claim(session, club.players[0], account)
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "777")

    assert await is_admin(session, account)
    assert await is_member(session, account, club.group_id)


async def test_an_admin_arriving_by_email_is_still_an_admin(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bug this pair exists to prevent, and it is invisible from inside one door.

    The two ways in mint **different accounts** — a magic link resolves by address, a bot
    link by account — so an admin who signed in by email held no Telegram identity, was
    refused everywhere, and had nothing on screen saying why.
    """
    by_email = await ensure_identity(session, PROVIDER_EMAIL, "boss@example.test")
    monkeypatch.setenv("ADMIN_EMAILS", "boss@example.test")
    monkeypatch.delenv("ADMIN_TELEGRAM_IDS", raising=False)

    assert await is_admin(session, by_email)


async def test_an_address_is_matched_whatever_its_case(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Addresses are stored lowercased; whoever types the setting will not know that."""
    by_email = await ensure_identity(session, PROVIDER_EMAIL, "boss@example.test")
    monkeypatch.setenv("ADMIN_EMAILS", "Boss@Example.TEST")

    assert await is_admin(session, by_email)


async def test_one_door_being_listed_does_not_open_the_other(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Telegram id in the address list must not match, or the lists are one list."""
    by_email = await ensure_identity(session, PROVIDER_EMAIL, "someone@example.test")
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "someone@example.test")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)

    assert not await is_admin(session, by_email)


async def test_an_admin_sees_every_group(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The list answers "what can I open", and for an admin that is everything.

    Narrower than the permission rule sends somebody hunting for a URL they are already
    allowed to visit — which is exactly what the empty list in a Mini App was.
    """
    club = await make_club(session)
    outsider = await ensure_identity(session, PROVIDER_TELEGRAM, "999")
    assert await groups_for_account(session, outsider) == []

    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "999")

    assert [view.id for view in await groups_for_account(session, outsider)] == [club.group_id]
