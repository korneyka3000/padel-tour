"""Invitations.

This is the one place where a person and a name on a roster are joined, so everything the
rest of the system trusts about identity rests on these rules holding.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, update

from conftest import account, make_club
from padel_tour.db import Invite, utc_now
from padel_tour.services import (
    add_player,
    create_group,
    create_invite,
    peek_invite,
    redeem_invite,
)
from padel_tour.services.errors import (
    AlreadyPlayingHereError,
    ForbiddenError,
    InviteNotFoundError,
    InviteUsedError,
    PlayerAlreadyClaimedError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def expire_everything(session: AsyncSession) -> None:
    await session.execute(update(Invite).values(expires_at=utc_now() - timedelta(seconds=1)))


# ------------------------------------------------------------------------------- issuing


async def test_only_the_owner_may_invite(session: AsyncSession) -> None:
    club = await make_club(session)
    stranger = await account(session, "stranger@example.test")

    with pytest.raises(ForbiddenError):
        await create_invite(session, stranger, club.player("Аня"))


async def test_a_claimed_player_is_not_offered_twice(session: AsyncSession) -> None:
    club = await make_club(session)
    anya = await account(session, "anya@example.test")
    await redeem_invite(session, await create_invite(session, club.owner, club.player("Аня")), anya)

    with pytest.raises(PlayerAlreadyClaimedError):
        await create_invite(session, club.owner, club.player("Аня"))


async def test_the_raw_token_is_never_stored(session: AsyncSession) -> None:
    club = await make_club(session)
    token = await create_invite(session, club.owner, club.player("Аня"))

    row = (await session.execute(select(Invite))).scalars().one()
    assert token not in row.token_hash


# ------------------------------------------------------------------------------ accepting


async def test_an_invitation_says_who_it_is_for_before_it_is_accepted(
    session: AsyncSession,
) -> None:
    """So the page can say "join as Аня" rather than asking someone to sign in blind."""
    club = await make_club(session)
    token = await create_invite(session, club.owner, club.player("Аня"))

    assert (await peek_invite(session, token)).name == "Аня"


async def test_an_invitation_binds_the_account_to_that_player(session: AsyncSession) -> None:
    club = await make_club(session)
    anya = await account(session, "anya@example.test")
    token = await create_invite(session, club.owner, club.player("Аня"))

    claimed = await redeem_invite(session, token, anya)
    assert claimed.id == club.player("Аня")


async def test_an_invitation_works_once(session: AsyncSession) -> None:
    """A link forwarded to the chat must not hand out the same person twice."""
    club = await make_club(session)
    anya = await account(session, "anya@example.test")
    impostor = await account(session, "impostor@example.test")
    token = await create_invite(session, club.owner, club.player("Аня"))
    await redeem_invite(session, token, anya)

    with pytest.raises(InviteUsedError):
        await redeem_invite(session, token, impostor)


async def test_an_expired_invitation_is_refused(session: AsyncSession) -> None:
    club = await make_club(session)
    anya = await account(session, "anya@example.test")
    token = await create_invite(session, club.owner, club.player("Аня"))
    await expire_everything(session)

    with pytest.raises(InviteNotFoundError):
        await redeem_invite(session, token, anya)


async def test_a_made_up_invitation_is_refused(session: AsyncSession) -> None:
    await make_club(session)
    somebody = await account(session, "somebody@example.test")

    with pytest.raises(InviteNotFoundError):
        await redeem_invite(session, "not-a-real-token", somebody)


async def test_two_invitations_for_one_player_still_yield_one_holder(
    session: AsyncSession,
) -> None:
    """The owner reissues a link they think was lost. Both are live; only one can win."""
    club = await make_club(session)
    first = await create_invite(session, club.owner, club.player("Аня"))
    second = await create_invite(session, club.owner, club.player("Аня"))
    anya = await account(session, "anya@example.test")
    impostor = await account(session, "impostor@example.test")

    await redeem_invite(session, first, anya)
    with pytest.raises(PlayerAlreadyClaimedError):
        await redeem_invite(session, second, impostor)


async def test_one_account_cannot_be_two_players_in_one_group(session: AsyncSession) -> None:
    """Otherwise a person collects a second set of results in the same standings."""
    club = await make_club(session)
    anya = await account(session, "anya@example.test")
    await redeem_invite(session, await create_invite(session, club.owner, club.player("Аня")), anya)

    with pytest.raises(AlreadyPlayingHereError):
        await redeem_invite(
            session, await create_invite(session, club.owner, club.player("Боря")), anya
        )


async def test_the_same_account_may_play_in_two_groups(session: AsyncSession) -> None:
    """Tuesday padel and Saturday padel are different rosters, one person."""
    tuesday = await make_club(session)
    anya = await account(session, "anya@example.test")
    await redeem_invite(
        session, await create_invite(session, tuesday.owner, tuesday.player("Аня")), anya
    )

    saturday = await create_group(session, "Субботний падел", owner_account_id=tuesday.owner.id)
    other = await add_player(session, saturday.id, "Анна", actor=tuesday.owner)

    claimed = await redeem_invite(
        session, await create_invite(session, tuesday.owner, other.id), anya
    )
    assert claimed.id == other.id
