"""Tokens are the whole of our authentication, so their properties are worth pinning."""

from __future__ import annotations

import re

from padel_tour.services.tokens import TOKEN_BYTES, hash_token, issue

#: Anything outside this needs escaping to survive a URL, and these tokens travel in links.
URL_SAFE = re.compile(r"^[A-Za-z0-9_-]+$")


def test_every_token_is_different() -> None:
    tokens = {issue()[0] for _ in range(100)}
    assert len(tokens) == 100


def test_the_hash_is_not_the_token() -> None:
    raw, hashed = issue()
    assert hashed != raw


def test_hashing_is_deterministic() -> None:
    """Otherwise a token could never be looked up."""
    raw, hashed = issue()
    assert hash_token(raw) == hashed


def test_a_token_survives_a_url_unescaped() -> None:
    raw, _ = issue()
    assert URL_SAFE.match(raw)


def test_a_token_carries_the_entropy_we_claim() -> None:
    raw, _ = issue()
    # base64url of 32 bytes, minus padding.
    assert len(raw) >= TOKEN_BYTES
