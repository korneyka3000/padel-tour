"""Single-use tokens for sign-in links and invitations.

Only the hash is ever stored. A leaked database is bad; a leaked database that lets someone
sign in as anyone is worse, and the difference costs one line.
"""

from __future__ import annotations

import hashlib
import secrets

#: 32 bytes of entropy, URL-safe. Long enough that guessing is not a threat model, short
#: enough to sit in a link someone pastes into a chat.
TOKEN_BYTES = 32


def issue() -> tuple[str, str]:
    """A new token: the value to hand out, and the hash to keep."""
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    """The stored form of a token.

    Plain SHA-256 rather than a password hash on purpose: these are 32 random bytes with no
    structure to guess, so the slow hashing that protects weak passwords buys nothing and
    would cost a second on every request that carries one.
    """
    return hashlib.sha256(raw.encode()).hexdigest()
