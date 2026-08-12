"""Every query in the application, and nothing else.

Until now these were spread through the service modules, mixed in with the rules they
served. That made two things hard: finding out what the application actually asks the
database, and auditing how it asks — which loads are eager, which filters are indexed, where
an N+1 could hide. "I cannot find where the queries are" is a fair complaint about a layer
that does not exist.

**What belongs here.** Building a statement, running it, and handing back rows. Loading
options are part of the query and live here too: a caller should not have to remember that
reading a tournament needs its entries and its rounds, and with ``lazy="raise_on_sql"`` on
every relationship, forgetting is an exception rather than a silent extra round trip.

**What does not.** Permissions, invariants, and anything that decides whether an absent row
is an error. A repository answers "is there one"; the service decides what that means. So
these functions return ``None`` and empty lists — they raise only when the database does.

Functions rather than classes, and a session per call rather than one held on an instance:
the transaction belongs to whoever started it, which is the middleware for a bot update and
the dependency for a request. A repository that owned a session would be a second opinion
about where a unit of work begins.
"""

from .accounts import (
    account_by_id,
    account_by_identity,
    add_identity,
    external_ids_of,
    login_session_by_token,
    magic_link_by_token,
    purge_dead_sessions,
    recent_magic_link,
    revoke,
    save,
    sessions_of,
)
from .groups import (
    active_player_count,
    group_by_id,
    group_by_link,
    group_by_name,
    group_ids_for_account,
    group_names,
    groups_with_counts,
    player_by_id,
    player_by_name,
    player_of_account,
    players_by_ids,
    players_of_group,
)
from .invites import invite_by_token, other_player_of_account
from .schema import ping, present_columns
from .tournaments import (
    active_tournament_row,
    count_tournaments_of,
    loaded,
    player_id_in_tournament,
    tournament_by_id,
    tournament_row,
    tournament_showing_chart,
    tournaments_of_account,
    tournaments_of_group,
    tournaments_of_player,
)

__all__ = [
    "account_by_id",
    "account_by_identity",
    "active_player_count",
    "active_tournament_row",
    "add_identity",
    "count_tournaments_of",
    "external_ids_of",
    "group_by_id",
    "group_by_link",
    "group_by_name",
    "group_ids_for_account",
    "group_names",
    "groups_with_counts",
    "invite_by_token",
    "loaded",
    "login_session_by_token",
    "magic_link_by_token",
    "other_player_of_account",
    "ping",
    "player_by_id",
    "player_by_name",
    "player_id_in_tournament",
    "player_of_account",
    "players_by_ids",
    "players_of_group",
    "present_columns",
    "purge_dead_sessions",
    "recent_magic_link",
    "revoke",
    "save",
    "sessions_of",
    "tournament_by_id",
    "tournament_row",
    "tournament_showing_chart",
    "tournaments_of_account",
    "tournaments_of_group",
    "tournaments_of_player",
]
