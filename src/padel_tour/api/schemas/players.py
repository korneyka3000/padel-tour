"""One player's record across everything they have played.

An alias, like the tournament schemas next door: :class:`~padel_tour.services.PlayerStats`
is the response. It used to be copied into a near-identical model field by field, which for
a profile meant ten lines of assignment and one real difference — the wire says ``id`` where
the service says ``player_id``. That difference is a ``serialization_alias`` on the field
now, rather than a class built to hold it.
"""

from __future__ import annotations

from padel_tour.services import PlayerStats

PlayerProfile = PlayerStats

__all__ = ["PlayerProfile"]
