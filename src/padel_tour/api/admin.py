"""The administrator's endpoints.

Every route here takes :data:`~padel_tour.api.deps.RequiredAdmin`, and that is the whole of
the access control — there is no route in this module that reads the actor for any other
reason, so forgetting the dependency is the only way to open a hole. A test walks the OpenAPI
document and refuses any ``/api/admin`` path that answers an ordinary account.

**Reading is general, writing is not.** ``/tables`` will show any table in the schema,
because an admin panel that only contains what somebody anticipated is the panel that will
not contain whatever broke. Writing goes through the service layer one operation at a time,
because a general editor over these tables could store a match score the engine considers
impossible — after which every standings calculation reads a state that cannot happen, and
nobody finds out for a week.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from padel_tour import repositories
from padel_tour.services import TableNotFoundError, list_groups
from padel_tour.services.admin import (
    AccountView,
    Doomed,
    Totals,
    all_tournaments,
    attach_player,
    delete_group,
    delete_tournament,
    detach_player,
    group_impact,
    list_accounts,
    set_owner,
    totals,
)

from .deps import API_PREFIX, RequiredAdmin, Session

if TYPE_CHECKING:
    from sqlalchemy import Column
from .schemas import Group, TournamentCard

router = APIRouter(prefix=f"{API_PREFIX}/admin", tags=["admin"])

#: Page sizes. Larger than the public ones — this is a list somebody scans, not a feed.
DEFAULT_PAGE = 50
MAX_PAGE = 200

#: Columns the table browser never returns, matched by name across every table.
#:
#: These are hashes, not tokens, so showing one grants nothing. They are withheld anyway:
#: there is no question an administrator answers by reading one, and a screen that displays
#: secret-shaped values teaches the habit of pasting them somewhere.
REDACTED = frozenset({"token_hash"})


class TableName(BaseModel):
    name: str
    rows: int


class Page(BaseModel):
    """One page of one table, as columns and rows rather than objects.

    Deliberately untyped: the point of this screen is to show whatever is there, including a
    column added last week that no model on this side knows about yet.
    """

    name: str
    columns: list[str]
    rows: list[dict[str, str | None]]
    total: int
    redacted: list[str] = Field(
        default_factory=list,
        description="Columns withheld from every row, so their absence is not a mystery",
    )


class OwnerChange(BaseModel):
    account_id: uuid.UUID | None = Field(
        default=None, description="None hands the group to nobody, which opens it to members"
    )


class Attachment(BaseModel):
    account_id: uuid.UUID


# ------------------------------------------------------------------------------- overview


@router.get("/totals")
async def read_totals(session: Session, _: RequiredAdmin) -> Totals:
    """How big this thing is. The only screen that asks."""
    return await totals(session)


# --------------------------------------------------------------------------------- people


@router.get("/accounts")
async def read_accounts(
    session: Session,
    _: RequiredAdmin,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AccountView]:
    """Everyone with an account, how they sign in, and when they were last here."""
    return await list_accounts(session, limit=limit, offset=offset)


@router.post("/players/{player_id}/attach", status_code=204)
async def attach(
    player_id: uuid.UUID, body: Attachment, session: Session, _: RequiredAdmin
) -> None:
    """Bind a roster name to somebody's account, without being that person."""
    await attach_player(session, player_id, body.account_id)


@router.post("/players/{player_id}/detach", status_code=204)
async def detach(player_id: uuid.UUID, session: Session, _: RequiredAdmin) -> None:
    """Let go of a player on behalf of whoever holds them. Asking twice is not an error."""
    await detach_player(session, player_id)


# --------------------------------------------------------------------------------- groups


@router.get("/groups")
async def read_groups(session: Session, _: RequiredAdmin) -> list[Group]:
    """Every group there is, not only the ones you belong to."""
    return await list_groups(session)


@router.get("/groups/{group_id}/impact")
async def read_impact(group_id: uuid.UUID, session: Session, _: RequiredAdmin) -> Doomed:
    """What deleting this group would destroy. Asked before the delete, never after."""
    return await group_impact(session, group_id)


@router.delete("/groups/{group_id}")
async def remove_group(group_id: uuid.UUID, session: Session, _: RequiredAdmin) -> Doomed:
    """Delete a group with its roster and every tournament it played.

    Answers what it took rather than 204, so the screen can say it out loud afterwards.
    """
    return await delete_group(session, group_id)


@router.put("/groups/{group_id}/owner", status_code=204)
async def change_owner(
    group_id: uuid.UUID, body: OwnerChange, session: Session, _: RequiredAdmin
) -> None:
    """Hand a group to somebody, or to nobody — which is how one stuck behind a departed
    owner gets unstuck."""
    await set_owner(session, group_id, body.account_id)


# ---------------------------------------------------------------------------- tournaments


@router.get("/tournaments")
async def read_tournaments(
    session: Session,
    _: RequiredAdmin,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TournamentCard]:
    """Every tournament across every group, newest first."""
    return await all_tournaments(session, limit=limit, offset=offset)


@router.delete("/tournaments/{tournament_id}", status_code=204)
async def remove_tournament(tournament_id: uuid.UUID, session: Session, _: RequiredAdmin) -> None:
    """Delete one tournament with its rounds and results. The group is left alone."""
    await delete_tournament(session, tournament_id)


# --------------------------------------------------------------------------------- tables


@router.get("/tables")
async def read_tables(session: Session, _: RequiredAdmin) -> list[TableName]:
    """Every table in the schema, with how many rows it holds."""
    return [
        TableName(name=name, rows=rows) for name, rows in await repositories.table_sizes(session)
    ]


@router.get("/tables/{name}")
async def read_table(
    name: str,
    session: Session,
    _: RequiredAdmin,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page:
    """One page of one table, exactly as it is stored.

    Read-only, and general on purpose: this is the part of the panel that still contains
    whatever broke, including a column no model here has heard of.
    """
    table = repositories.table_named(name)
    if table is None:
        raise TableNotFoundError(f"no table called {name}", name=name)

    shown = [column for column in table.columns if column.name not in REDACTED]
    rows = await repositories.read_page(session, table, shown, limit=limit, offset=offset)

    return Page(
        name=name,
        columns=[column.name for column in shown],
        rows=[_as_text(shown, row) for row in rows],
        total=await repositories.count_rows(session, table),
        redacted=sorted(column.name for column in table.columns if column.name in REDACTED),
    )


def _as_text(columns: Sequence[Column[object]], row: Sequence[object]) -> dict[str, str | None]:
    """One row, every value stringified.

    A browser over twelve tables meets UUIDs, enums, timestamps and JSON, and typing that
    honestly on the wire would mean describing every table twice. The screen only ever
    displays these, so text is the true shape of what it needs.
    """
    return {
        column.name: None if value is None else str(value)
        for column, value in zip(columns, row, strict=True)
    }


__all__ = ["router"]
