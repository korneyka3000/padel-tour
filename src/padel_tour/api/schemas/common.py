"""What every endpoint might answer with."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str
    database: str


class ErrorBody(BaseModel):
    """What a refusal looks like.

    Three fields because two audiences read it. ``detail`` is English and goes in the log;
    ``code`` and ``params`` let an interface say the same thing in its own language, with
    its own agreement rules. A client that does not know a code falls back to ``detail`` —
    an old page against a new server should show an awkward sentence, not an empty one.
    """

    detail: str
    code: str = ""
    params: dict[str, object] = Field(default_factory=dict)
