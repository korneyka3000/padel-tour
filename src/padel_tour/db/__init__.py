"""Storage layer: models, engine and sessions.

Nothing here knows the rules of padel — that is the engine's job. Nothing here decides what
a user is allowed to do — that is the service layer's job.
"""

from .config import DEFAULT_SQLITE_PATH, database_url, is_sqlite, normalise_url
from .models import (
    Base,
    Group,
    Match,
    Player,
    Round,
    Tournament,
    TournamentPlayer,
    TournamentStatus,
    new_id,
    utc_now,
)
from .session import (
    create_all,
    create_engine,
    create_session_factory,
    drop_all,
    session_scope,
)

__all__ = [
    "DEFAULT_SQLITE_PATH",
    "Base",
    "Group",
    "Match",
    "Player",
    "Round",
    "Tournament",
    "TournamentPlayer",
    "TournamentStatus",
    "create_all",
    "create_engine",
    "create_session_factory",
    "database_url",
    "drop_all",
    "is_sqlite",
    "new_id",
    "normalise_url",
    "session_scope",
    "utc_now",
]
