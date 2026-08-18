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
    all_accounts,
    count_account_rows,
    count_accounts,
    drop_account,
    external_ids_of,
    identities_of,
    identity_providers_of,
    last_seen_of,
    login_session_by_token,
    magic_link_by_token,
    move_account_rows,
    player_groups_of,
    players_of_accounts,
    purge_dead_sessions,
    recent_magic_link,
    revoke,
    save,
    sessions_of,
)
from .groups import (
    active_player_count,
    count_groups,
    count_players,
    counts_under,
    drop_group,
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
from .schema import count_rows, ping, present_columns, read_page, table_named, table_sizes
from .tournaments import (
    active_tournament_row,
    all_tournaments,
    count_all_tournaments,
    count_tournaments_of,
    drop_tournament,
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
    "all_accounts",
    "all_tournaments",
    "count_account_rows",
    "count_accounts",
    "count_all_tournaments",
    "count_groups",
    "count_players",
    "count_rows",
    "count_tournaments_of",
    "counts_under",
    "drop_account",
    "drop_group",
    "drop_tournament",
    "external_ids_of",
    "group_by_id",
    "group_by_link",
    "group_by_name",
    "group_ids_for_account",
    "group_names",
    "groups_with_counts",
    "identities_of",
    "identity_providers_of",
    "invite_by_token",
    "last_seen_of",
    "loaded",
    "login_session_by_token",
    "magic_link_by_token",
    "move_account_rows",
    "other_player_of_account",
    "ping",
    "player_by_id",
    "player_by_name",
    "player_groups_of",
    "player_id_in_tournament",
    "player_of_account",
    "players_by_ids",
    "players_of_accounts",
    "players_of_group",
    "present_columns",
    "purge_dead_sessions",
    "read_page",
    "recent_magic_link",
    "revoke",
    "save",
    "sessions_of",
    "table_named",
    "table_sizes",
    "tournament_by_id",
    "tournament_row",
    "tournament_showing_chart",
    "tournaments_of_account",
    "tournaments_of_group",
    "tournaments_of_player",
]
