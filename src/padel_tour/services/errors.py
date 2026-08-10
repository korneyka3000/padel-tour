"""Errors raised by the service layer.

Engine errors pass through untouched — they already say what went wrong in words a person
can act on. What is added here is everything the engine cannot know about: whether a group
exists, whether this player belongs to it, whether a tournament is already running.
"""

from __future__ import annotations

from padel_tour.faults import CodedError


class ServiceError(CodedError):
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


class AuthError(ServiceError):
    """Something went wrong signing in."""


class InvalidTokenError(AuthError):
    """No such token, or it has already been used."""


class TokenExpiredError(AuthError):
    """The token was real but is past its time."""


class TooManyRequestsError(ServiceError):
    """Asked again too soon.

    Sign-in links are sent to an address nobody has proved they own, so without this the
    form is a way to fill a stranger's inbox.
    """


class ForbiddenError(ServiceError):
    """Signed in, but not allowed to do this.

    Subclassed rather than raised directly, because the code is what an interface has to
    translate, and one code for every refusal would collapse "you are not in this group"
    and "you did not play this match" into the same unhelpful sentence.
    """


class NotAMemberError(ForbiddenError):
    """Not in this group."""


class NotTheOwnerError(ForbiddenError):
    """Only the group's owner keeps its roster."""


class NotTheOrganiserError(ForbiddenError):
    """Only whoever started this tournament can end or redraw it."""


class NotOnThisCourtError(ForbiddenError):
    """A known player of this tournament, but not one of the four who played this match."""


class NoActiveTournamentError(ServiceError):
    """Nothing is being played in this group right now."""


class NoTournamentsYetError(ServiceError):
    """This group has never played."""


class UnidentifiedCallerError(ServiceError):
    """There is nobody to attribute this to.

    A channel post has no sender. Passing "nobody" downstream would read as *system*, which
    skips every permission check, so it stops here instead.
    """


class NotSignedInError(AuthError):
    """Nobody is signed in, and this needs somebody.

    Separate from :class:`ForbiddenError` because the two ask for different things: one
    wants a sign-in form, the other wants an invitation.
    """


class InviteNotFoundError(NotFoundError):
    """No such invitation, or it has expired."""


class InviteUsedError(ConflictError):
    """That invitation has already been accepted."""


class PlayerAlreadyClaimedError(ConflictError):
    """Someone else already holds this player."""


class AlreadyPlayingHereError(ConflictError):
    """This account is already a different player in the same group."""
