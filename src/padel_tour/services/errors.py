"""Errors raised by the service layer.

Engine errors pass through untouched — they already say what went wrong in words a person
can act on. What is added here is everything the engine cannot know about: whether a group
exists, whether this player belongs to it, whether a tournament is already running.
"""

from __future__ import annotations


class ServiceError(Exception):
    """Base class for every service-layer error."""


class NotFoundError(ServiceError):
    """Something referenced by id does not exist."""


class GroupNotFoundError(NotFoundError):
    """No group with that id."""


class PlayerNotFoundError(NotFoundError):
    """No player with that id."""


class TournamentNotFoundError(NotFoundError):
    """No tournament with that id."""


class ConflictError(ServiceError):
    """The request is well-formed but conflicts with what already exists."""


class DuplicateGroupNameError(ConflictError):
    """A group with that name is already registered."""


class DuplicatePlayerNameError(ConflictError):
    """That name is already taken inside this group."""


class PlayerNotInGroupError(ServiceError):
    """A player was entered into a tournament belonging to a different group."""


class InactivePlayerError(ServiceError):
    """A deactivated player cannot be entered into a new tournament."""


class ActiveTournamentExistsError(ConflictError):
    """The group already has a tournament in progress.

    A group runs one tournament at a time: the bot shows a single screen per chat, and a
    second live tournament would make that screen ambiguous.
    """
