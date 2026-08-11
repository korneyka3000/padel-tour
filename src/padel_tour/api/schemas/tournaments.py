"""A tournament, on the wire.

Almost nothing left. This file used to hold a parallel set of models — ``Tournament``,
``Round``, ``Match``, ``Standing``, ``PlayerProgress`` — each mirroring a view in
``services.views`` field for field, plus the ``of()`` classmethods that copied one into the
other. ``Tournament.of`` was fifty lines whose only possible behaviour was to agree with the
class it was copying from, and whose only possible bug was not to.

The views are the wire format now. Fields a client must not see are marked
``Field(exclude=True)`` on the view itself, which is both shorter and stronger: the old
arrangement dropped ``organiser_account_id`` by not mentioning it, so adding a field to the
view and forgetting to add it here was invisible, while adding a *secret* to the view and
forgetting to exclude it here was a leak.

The names below are aliases, kept because a route reads better returning ``Tournament`` than
``TournamentView`` and because they are what the OpenAPI document and every import already
say.
"""

from __future__ import annotations

from padel_tour.services import (
    MatchView,
    PlayerProgress,
    ProgressPointView,
    RoundView,
    StandingView,
    TournamentSummary,
    TournamentView,
    Viewing,
)

#: A sane ceiling on a Mexicano. The engine has no opinion; a form field does need one.
MAX_ROUNDS = 40

Tournament = TournamentView
TournamentCard = TournamentSummary
Match = MatchView
Round = RoundView
Standing = StandingView
ProgressPoint = ProgressPointView
Viewer = Viewing

__all__ = [
    "MAX_ROUNDS",
    "Match",
    "PlayerProgress",
    "ProgressPoint",
    "Round",
    "Standing",
    "Tournament",
    "TournamentCard",
    "Viewer",
]
