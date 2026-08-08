"""Service layer — the single entry point for every interface.

The CLI, the Telegram bot and the future HTTP API all call these functions. They never talk
to the engine or the database directly, which is what keeps the bot and the web from
drifting apart in the details.

Every function takes a session first and **does not commit**: the caller owns the
transaction, so several calls can be composed into one unit of work.
"""

from .errors import (
    ActiveTournamentExistsError,
    ConflictError,
    DuplicateGroupNameError,
    DuplicatePlayerNameError,
    GroupNotFoundError,
    InactivePlayerError,
    NotFoundError,
    PlayerNotFoundError,
    PlayerNotInGroupError,
    ServiceError,
    TournamentNotFoundError,
)
from .groups import (
    add_player,
    bind_group_to_chat,
    create_group,
    deactivate_player,
    group_by_chat,
    list_groups,
    list_players,
    rename_player,
)
from .tournaments import (
    active_tournament,
    advance_round,
    amend_score,
    count_tournaments,
    finish_tournament,
    get_tournament,
    list_tournaments,
    player_history,
    record_score,
    reroll_tournament,
    start_tournament,
)
from .views import (
    GroupView,
    MatchView,
    PlayerView,
    RoundView,
    StandingView,
    TournamentSummary,
    TournamentView,
)

__all__ = [
    "ActiveTournamentExistsError",
    "ConflictError",
    "DuplicateGroupNameError",
    "DuplicatePlayerNameError",
    "GroupNotFoundError",
    "GroupView",
    "InactivePlayerError",
    "MatchView",
    "NotFoundError",
    "PlayerNotFoundError",
    "PlayerNotInGroupError",
    "PlayerView",
    "RoundView",
    "ServiceError",
    "StandingView",
    "TournamentNotFoundError",
    "TournamentSummary",
    "TournamentView",
    "active_tournament",
    "add_player",
    "advance_round",
    "amend_score",
    "bind_group_to_chat",
    "count_tournaments",
    "create_group",
    "deactivate_player",
    "finish_tournament",
    "get_tournament",
    "group_by_chat",
    "list_groups",
    "list_players",
    "list_tournaments",
    "player_history",
    "record_score",
    "rename_player",
    "reroll_tournament",
    "start_tournament",
]
