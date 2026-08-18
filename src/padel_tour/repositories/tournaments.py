"""Tournaments, and what has to be loaded with one for the engine to rebuild it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from padel_tour.db import Player, Round, Tournament, TournamentPlayer, TournamentStatus

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.base import ExecutableOption


def loaded() -> tuple[ExecutableOption, ...]:
    """Everything the mapper needs to rebuild a tournament, in two extra queries.

    Not an optimisation — a requirement. Relationships are ``lazy="raise_on_sql"``, so a
    tournament fetched without these raises the moment anything reads its rounds, and the
    engine reads all of them. Stated here once rather than remembered at eight call sites.
    """
    return (
        selectinload(Tournament.entries).selectinload(TournamentPlayer.player),
        selectinload(Tournament.rounds).selectinload(Round.matches),
    )


async def tournament_by_id(
    session: AsyncSession, tournament_id: uuid.UUID, *, fresh: bool = False
) -> Tournament | None:
    """One tournament, loaded whole.

    ``fresh`` re-reads rows already in the identity map. Needed straight after a write:
    a Mexicano round created in this transaction, or the entries a reroll rebuilt, have
    nothing loaded behind them, and reaching through to a player's name would be the lazy
    load that ``raise_on_sql`` forbids.
    """
    query = select(Tournament).where(Tournament.id == tournament_id).options(*loaded())
    if fresh:
        query = query.execution_options(populate_existing=True)
    return await session.scalar(query)


async def active_tournament_row(session: AsyncSession, group_id: uuid.UUID) -> Tournament | None:
    """The one in progress, newest first — a group runs one at a time."""
    return await session.scalar(
        select(Tournament)
        .where(Tournament.group_id == group_id, Tournament.status == TournamentStatus.ACTIVE)
        .order_by(Tournament.created_at.desc())
        .options(*loaded())
    )


async def tournaments_of_group(
    session: AsyncSession, group_id: uuid.UUID, *, limit: int, offset: int
) -> Sequence[Tournament]:
    return list(
        await session.scalars(
            select(Tournament)
            .where(Tournament.group_id == group_id)
            .order_by(Tournament.created_at.desc())
            .limit(limit)
            .offset(offset)
            .options(*loaded())
        )
    )


async def tournaments_of_player(
    session: AsyncSession, player_id: uuid.UUID
) -> Sequence[Tournament]:
    return list(
        await session.scalars(
            select(Tournament)
            .join(TournamentPlayer, TournamentPlayer.tournament_id == Tournament.id)
            .where(TournamentPlayer.player_id == player_id)
            .order_by(Tournament.created_at.desc())
            .options(*loaded())
        )
    )


async def tournaments_of_account(
    session: AsyncSession, account_id: uuid.UUID, *, limit: int, offset: int
) -> Sequence[Tournament]:
    """Everything this person has played, across every group they play in.

    Reached through the players they have claimed, which is the only link an account has to
    a tournament: a group's roster is names, and an account attaches to one of those names.
    Somebody who has claimed nobody has played nothing, as far as this can tell — which is
    correct, and is what an invitation fixes.
    """
    return list(
        await session.scalars(
            select(Tournament)
            .join(TournamentPlayer, TournamentPlayer.tournament_id == Tournament.id)
            .join(Player, Player.id == TournamentPlayer.player_id)
            .where(Player.account_id == account_id)
            .order_by(Tournament.created_at.desc())
            .limit(limit)
            .offset(offset)
            .options(*loaded())
        )
    )


async def count_tournaments_of(session: AsyncSession, group_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.count(Tournament.id)).where(Tournament.group_id == group_id)
    )
    return int(total or 0)


async def tournament_row(session: AsyncSession, tournament_id: uuid.UUID) -> Tournament | None:
    """The row on its own, with nothing loaded behind it.

    For the questions that only need columns — who organises this, which group is it — where
    fetching the rounds as well would be two queries nobody reads.
    """
    return await session.get(Tournament, tournament_id)


async def player_id_in_tournament(
    session: AsyncSession, tournament_id: uuid.UUID, account_id: uuid.UUID
) -> uuid.UUID | None:
    """The player this account holds in this tournament, if they have claimed one."""
    return await session.scalar(
        select(Player.id)
        .join(TournamentPlayer, TournamentPlayer.player_id == Player.id)
        .where(TournamentPlayer.tournament_id == tournament_id, Player.account_id == account_id)
    )


async def tournament_showing_chart(session: AsyncSession, group_id: uuid.UUID) -> Tournament | None:
    """Whichever tournament in this group currently has a chart posted, if any.

    Looked up by group rather than by tournament because the caller is any other button
    press, and it does not know — or care — which tournament the picture belonged to.
    """
    return await session.scalar(
        select(Tournament).where(
            Tournament.group_id == group_id, Tournament.chart_message_id.is_not(None)
        )
    )


async def all_tournaments(
    session: AsyncSession, *, limit: int, offset: int
) -> Sequence[Tournament]:
    """Every tournament there is, newest first. The admin list."""
    return list(
        await session.scalars(
            select(Tournament)
            .order_by(Tournament.created_at.desc())
            .limit(limit)
            .offset(offset)
            .options(*loaded())
        )
    )


async def drop_tournament(session: AsyncSession, row: Tournament) -> None:
    """Delete a tournament with its rounds, matches and roster entries."""
    await session.delete(row)
    await session.flush()


async def count_all_tournaments(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(Tournament.id))) or 0)
