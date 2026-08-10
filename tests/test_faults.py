"""Error codes, and the promise that somebody has written words for every one of them.

The code is derived from the class name, so it cannot drift from the class. What *can*
drift is the wording: add an exception, forget the phrase, and the bot quietly starts
showing English to a Russian chat. That is the kind of regression nobody files a bug about
— they just think the bot is broken — so it gets a test.
"""

from __future__ import annotations

from padel_tour.bot.wording import PHRASES, say
from padel_tour.engine.errors import PadelEngineError
from padel_tour.faults import CodedError, code_for
from padel_tour.services.errors import PlayerAlreadyClaimedError, ServiceError


def descendants(root: type[CodedError]) -> set[type[CodedError]]:
    """Every concrete error under a base, however deep the hierarchy goes."""
    found: set[type[CodedError]] = set()
    stack = [root]
    while stack:
        current = stack.pop()
        found.add(current)
        stack.extend(current.__subclasses__())
    return found


def test_a_code_is_the_class_name_in_snake_case() -> None:
    class PlayerAlreadyClaimedError(CodedError): ...

    class NotSignedInError(CodedError): ...

    class NotAMemberError(CodedError): ...

    assert code_for(PlayerAlreadyClaimedError) == "player_already_claimed"
    assert code_for(NotSignedInError) == "not_signed_in"
    # The one that caught the naive rule: a single-letter word runs into the next one and
    # comes out as "not_amember" unless consecutive capitals are handled too.
    assert code_for(NotAMemberError) == "not_a_member"


def test_every_error_the_bot_can_raise_has_russian_words() -> None:
    """Both hierarchies, every leaf, no exceptions granted.

    Leaves only: a class with subclasses is a family that exists to be caught, not raised —
    ``NotFoundError`` and ``ConflictError`` map onto status codes and never reach a person
    by themselves. Nothing raises one bare, and the heuristic needs no list to maintain.
    """
    missing = sorted(
        error.__name__
        for base in (ServiceError, PadelEngineError)
        for error in descendants(base)
        if not error.__subclasses__() and code_for(error) not in PHRASES
    )

    assert missing == [], f"no Russian phrase for: {', '.join(missing)}"


def test_a_parameter_lands_inside_the_sentence() -> None:
    """Params travel beside the message so the wording can put them where its grammar
    wants them, which is not where English put them."""
    spoken = say(PlayerAlreadyClaimedError("Аня is already claimed", name="Аня"))

    assert spoken == "Аня уже занят(а)"


def test_an_unknown_code_falls_back_to_the_english() -> None:
    """A phrase nobody wrote yet still beats a shrug: it says what happened, and a
    screenshot of it is a bug report somebody can act on."""

    class SomethingNobodyPhrasedError(ServiceError): ...

    assert say(SomethingNobodyPhrasedError("the thing went sideways")) == "the thing went sideways"
