"""Giving an error a name a machine can act on.

Messages are English, because that is the rule for everything in ``src`` and because the
first reader of an exception is usually a log, not a person. But an English sentence is no
use to somebody looking at a Russian interface, so every error also carries a **code** and
the **parameters** its sentence was built from. The client picks the wording; the server
picks the meaning.

The code is derived from the class name rather than declared:

    PlayerAlreadyClaimedError  ->  "player_already_claimed"

A hand-written registry would be a second list of the same facts, and the two would part
company the first time somebody renamed a class without grepping. Deriving it means the
code cannot be wrong, only different — and a renamed class changing its code is exactly
what should happen, since it is a different error now.

Parameters travel beside the message instead of baked into it. A client that receives
``{"name": "Аня"}`` can build a sentence that agrees in gender and case; one that receives
only ``"Аня is already taken"`` can do nothing but show it.
"""

from __future__ import annotations

import re

#: Where one word ends and the next begins inside a class name.
#:
#: Two boundaries, not one. The obvious rule — lowercase followed by uppercase — turns
#: ``NotAMemberError`` into ``not_amember``, because the single-letter word runs straight
#: into the next one. The second alternative catches that: an uppercase letter followed by
#: an uppercase-then-lowercase pair starts a new word.
_WORD_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def code_for(kind: type[BaseException]) -> str:
    """``NotSignedInError`` -> ``not_signed_in``."""
    name = kind.__name__.removesuffix("Error")
    return "_".join(part.lower() for part in _WORD_BOUNDARY.split(name))


class CodedError(Exception):
    """An error that knows what kind of error it is.

    Subclass hierarchies stay as they are — catching ``ServiceError`` or ``NotFoundError``
    still works, and the layers above still map families onto status codes. This only adds
    the two things a client needs to say the same thing in its own words.
    """

    def __init__(self, message: str = "", /, **params: object) -> None:
        super().__init__(message)
        #: Typed ``object`` rather than ``Any``: these values are passed through to JSON
        #: and interpolated by the client. Nothing here calls a method on them.
        self.params: dict[str, object] = params

    @property
    def code(self) -> str:
        return code_for(type(self))


__all__ = ["CodedError", "code_for"]
