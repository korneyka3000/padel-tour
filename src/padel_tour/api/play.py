"""Running a tournament from the browser.

Transport only. Every rule these routes enforce is enforced one layer down, inside the
service functions, because the bot calls those directly and must not be able to skip a check
by not going through HTTP. Nothing here decides anything; it turns a request into one call
and the answer into JSON.

Each write answers with the **whole tournament**. A score changes the standings, the chart,
and — in a Mexicano — who plays whom next; sending back the one match would only force a
second request for what the server has just finished computing.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from padel_tour.db import Account
from padel_tour.engine import Format, PairingPattern, TournamentConfig
from padel_tour.services import (
    TournamentView,
    advance_round,
    amend_score,
    finish_tournament,
    get_tournament,
    record_score,
    reroll_tournament,
    start_tournament,
    viewing,
)

from .deps import API_PREFIX, RequiredAccount, Session
from .schemas import Tournament

router = APIRouter(prefix=API_PREFIX, tags=["play"])

#: A sane ceiling on a Mexicano. The engine has no opinion; a form field does need one.
MAX_ROUNDS = 40


class NewTournament(BaseModel):
    player_ids: list[uuid.UUID] = Field(min_length=1)
    format: Format
    points_per_match: int = Field(default=24, ge=2)
    pairing_pattern: PairingPattern = PairingPattern.CROSSOVER
    rounds: int | None = Field(default=None, ge=1, le=MAX_ROUNDS)

    def config(self) -> TournamentConfig:
        """The engine's idea of the same thing.

        ``rounds`` is dropped for an Americano, which plays a fixed ``n - 1`` and refuses a
        round count outright. The screen keeps one form for both formats, so the field is
        filled in either way; ignoring it here matches how ``pairing_pattern`` already
        behaves for Americano and keeps the refusals for things the organiser can act on.
        """
        return TournamentConfig(
            format=self.format,
            points_per_match=self.points_per_match,
            pairing_pattern=self.pairing_pattern,
            rounds=None if self.format is Format.AMERICANO else self.rounds,
        )


class NewScore(BaseModel):
    score_a: int = Field(ge=0)
    score_b: int = Field(ge=0)


async def _rendered(session: AsyncSession, view: TournamentView, actor: Account) -> Tournament:
    """A tournament plus where this caller stands in it.

    Every write goes out through here, so no route can forget the part that decides which
    buttons the next screen is allowed to draw.
    """
    return Tournament.of(view, await viewing(session, actor, view))


@router.post("/groups/{group_id}/tournaments", status_code=status.HTTP_201_CREATED)
async def draw_tournament(
    group_id: uuid.UUID, body: NewTournament, session: Session, actor: RequiredAccount
) -> Tournament:
    """Draw a tournament for a group. Whoever draws it organises it.

    The roster is validated by the engine, which is the only place that knows an Americano
    needs a multiple of four and can say so in a sentence an organiser can act on.
    """
    view = await start_tournament(session, group_id, body.player_ids, body.config(), actor=actor)
    return await _rendered(session, view, actor)


@router.post("/tournaments/{tournament_id}/reroll")
async def redraw(tournament_id: uuid.UUID, session: Session, actor: RequiredAccount) -> Tournament:
    """Redraw before the first result. The engine refuses once play has started."""
    view = await reroll_tournament(session, tournament_id, actor=actor)
    return await _rendered(session, view, actor)


@router.put("/tournaments/{tournament_id}/rounds/{round_no}/courts/{court}")
async def put_score(
    tournament_id: uuid.UUID,
    round_no: int,
    court: int,
    body: NewScore,
    session: Session,
    actor: RequiredAccount,
) -> Tournament:
    """Set this match's score, first time or correcting it.

    One verb for what the service layer splits in two. ``record_score`` refuses a match that
    already has a result — a guard the bot needs, where the same button can be pressed twice
    — but a phone showing the current score is not entering it twice, it is entering what it
    now says. Which of the two applies is a fact about stored state, so the server reads it
    rather than making the client declare it.
    """
    current = await get_tournament(session, tournament_id)
    already = any(
        match.played
        for rnd in current.rounds
        if rnd.number == round_no
        for match in rnd.matches
        if match.court == court
    )
    write = amend_score if already else record_score
    view = await write(
        session,
        tournament_id,
        round_no=round_no,
        court=court,
        score_a=body.score_a,
        score_b=body.score_b,
        actor=actor,
    )
    return await _rendered(session, view, actor)


@router.post("/tournaments/{tournament_id}/next-round")
async def next_round(
    tournament_id: uuid.UUID, session: Session, actor: RequiredAccount
) -> Tournament:
    """Draw the next Mexicano round from the standing as it now is."""
    view = await advance_round(session, tournament_id, actor=actor)
    return await _rendered(session, view, actor)


@router.post("/tournaments/{tournament_id}/finish")
async def finish(tournament_id: uuid.UUID, session: Session, actor: RequiredAccount) -> Tournament:
    """End it wherever it stands. Eleven rounds is two and a half hours; people leave."""
    view = await finish_tournament(session, tournament_id, actor=actor)
    return await _rendered(session, view, actor)


__all__ = ["router"]
