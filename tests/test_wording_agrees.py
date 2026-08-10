"""The two phrasebooks must cover the same refusals.

The bot translates error codes in Python; the web translates the same codes in TypeScript.
Nothing but this test connects them, and without it the usual failure is silent and
one-sided: somebody adds an error, writes the Russian for the bot because that is the file
they are in, and the web starts showing English to the same people.

Reading the TypeScript with a regex is crude. It is also the only thing here that would
have caught that, and it costs one file.
"""

from __future__ import annotations

import re
from pathlib import Path

from padel_tour.bot.wording import PHRASES

DICTIONARY = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "i18n.ts"

#: ``'error.not_signed_in': '…'`` in either dictionary.
_ENTRY = re.compile(r"'error\.([a-z0-9_]+)'\s*:")


def web_codes() -> set[str]:
    return set(_ENTRY.findall(DICTIONARY.read_text(encoding="utf-8")))


def test_the_web_has_words_for_every_code_the_bot_does() -> None:
    missing = sorted(set(PHRASES) - web_codes())

    assert missing == [], f"web/src/lib/i18n.ts has no phrase for: {', '.join(missing)}"


def test_the_bot_has_words_for_every_code_the_web_does() -> None:
    missing = sorted(web_codes() - set(PHRASES))

    assert missing == [], f"bot/wording.py has no phrase for: {', '.join(missing)}"
