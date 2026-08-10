"""What the API puts on the wire.

Split by resource rather than kept beside the handlers. A router's job is to turn a request
into one service call; the shape of the document is a separate concern with a separate
audience — the client reads it, and reads it as a whole rather than one endpoint at a time.
Keeping the two together also meant the same model could not be answered by two routers
without one importing the other.

Deliberately separate from the service layer's views as well. A ``TournamentView`` carries a
whole ``TournamentState`` for callers that need to ask the engine something; none of that
belongs in JSON, and keeping the two apart means the wire format can change without dragging
the service layer with it.
"""

from .auth import Accepted, EnterRequest, LaunchRequest, MagicLinkRequest, Me
from .common import ErrorBody, Health
from .groups import (
    MAX_NAME,
    Group,
    GroupDetail,
    NewGroup,
    NewPlayer,
    Player,
    RenamedPlayer,
)
from .invites import Invitation, RedeemRequest
from .play import NewScore, NewTournament
from .players import PlayerProfile
from .tournaments import (
    MAX_ROUNDS,
    Match,
    PlayerProgress,
    ProgressPoint,
    Round,
    Standing,
    Tournament,
    TournamentCard,
    Viewer,
)

__all__ = [
    "MAX_NAME",
    "MAX_ROUNDS",
    "Accepted",
    "EnterRequest",
    "ErrorBody",
    "Group",
    "GroupDetail",
    "Health",
    "Invitation",
    "LaunchRequest",
    "MagicLinkRequest",
    "Match",
    "Me",
    "NewGroup",
    "NewPlayer",
    "NewScore",
    "NewTournament",
    "Player",
    "PlayerProfile",
    "PlayerProgress",
    "ProgressPoint",
    "RedeemRequest",
    "RenamedPlayer",
    "Round",
    "Standing",
    "Tournament",
    "TournamentCard",
    "Viewer",
]
