"""The identity model, and the constraints that keep it honest.

Our `Account` is primary; Telegram, email and anything later are rows in `identities`.
These tests pin the invariants that make that claim real rather than decorative.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from padel_tour.db import (
    PROVIDER_EMAIL,
    PROVIDER_TELEGRAM,
    Account,
    Group,
    GroupLink,
    Identity,
    Player,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def make_account(session: AsyncSession, name: str = "Аня") -> Account:
    account = Account(display_name=name)
    session.add(account)
    await session.flush()
    return account


async def test_one_external_login_leads_to_one_account(session: AsyncSession) -> None:
    """Otherwise the same Telegram user could sign in as two different people."""
    first = await make_account(session, "Аня")
    second = await make_account(session, "Боря")

    session.add(Identity(account_id=first.id, provider=PROVIDER_TELEGRAM, external_id="42"))
    await session.flush()

    session.add(Identity(account_id=second.id, provider=PROVIDER_TELEGRAM, external_id="42"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_the_same_external_id_may_repeat_across_providers(
    session: AsyncSession,
) -> None:
    """A Telegram id of 42 and an email of "42" are unrelated facts."""
    account = await make_account(session)
    session.add_all(
        [
            Identity(account_id=account.id, provider=PROVIDER_TELEGRAM, external_id="42"),
            Identity(account_id=account.id, provider=PROVIDER_EMAIL, external_id="42"),
        ]
    )
    await session.flush()


async def test_an_account_has_at_most_one_login_per_provider(
    session: AsyncSession,
) -> None:
    account = await make_account(session)
    session.add(Identity(account_id=account.id, provider=PROVIDER_EMAIL, external_id="a@b.c"))
    await session.flush()

    session.add(Identity(account_id=account.id, provider=PROVIDER_EMAIL, external_id="x@y.z"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_one_person_cannot_be_two_players_in_a_group(session: AsyncSession) -> None:
    account = await make_account(session)
    group = Group(name="Вторник")
    session.add(group)
    await session.flush()

    session.add(Player(group_id=group.id, name="Аня", account_id=account.id))
    await session.flush()

    session.add(Player(group_id=group.id, name="Анна", account_id=account.id))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_the_same_person_may_play_in_two_groups(session: AsyncSession) -> None:
    account = await make_account(session)
    tuesday, thursday = Group(name="Вторник"), Group(name="Четверг")
    session.add_all([tuesday, thursday])
    await session.flush()

    session.add_all(
        [
            Player(group_id=tuesday.id, name="Аня", account_id=account.id),
            Player(group_id=thursday.id, name="Аня", account_id=account.id),
        ]
    )
    await session.flush()


async def test_players_without_an_account_do_not_collide(session: AsyncSession) -> None:
    """Playing must never require signing up, so unclaimed players are the normal case."""
    group = Group(name="Вторник")
    session.add(group)
    await session.flush()

    session.add_all(
        [
            Player(group_id=group.id, name="Аня"),
            Player(group_id=group.id, name="Боря"),
        ]
    )
    await session.flush()


async def test_an_external_chat_belongs_to_one_group(session: AsyncSession) -> None:
    tuesday, thursday = Group(name="Вторник"), Group(name="Четверг")
    session.add_all([tuesday, thursday])
    await session.flush()

    session.add(GroupLink(group_id=tuesday.id, provider=PROVIDER_TELEGRAM, external_id="-100500"))
    await session.flush()

    session.add(GroupLink(group_id=thursday.id, provider=PROVIDER_TELEGRAM, external_id="-100500"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_deleting_an_account_does_not_delete_the_player(
    session: AsyncSession,
) -> None:
    """History outlives an account: the tournaments a person played still happened."""
    account = await make_account(session)
    group = Group(name="Вторник")
    session.add(group)
    await session.flush()

    player = Player(group_id=group.id, name="Аня", account_id=account.id)
    session.add(player)
    await session.flush()

    await session.delete(account)
    await session.flush()

    await session.refresh(player)
    assert player.name == "Аня"
    assert player.account_id is None


async def test_a_group_records_who_owns_it(session: AsyncSession) -> None:
    account = await make_account(session)
    group = Group(name="Вторник", owner_account_id=account.id)
    session.add(group)
    await session.flush()
    assert group.owner_account_id == account.id


def test_provider_names_are_stable() -> None:
    """These strings sit in rows and in links people have already been sent."""
    assert PROVIDER_EMAIL == "email"
    assert PROVIDER_TELEGRAM == "telegram"


def test_identity_ids_are_uuids() -> None:
    assert isinstance(uuid.uuid7(), uuid.UUID)
