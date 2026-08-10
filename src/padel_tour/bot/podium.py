"""The card a tournament ends on.

Two hours on court deserve more of an ending than a list going grey. This draws the one
image the group will screenshot and send to whoever missed it: three blocks, the winner
raised, and — below the podium — everybody else, because seven of the eight also turned up
and played every round.

Deliberately not a leaderboard with a crown stuck on top. The podium is the part people look
at; the standings underneath are the part they check.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

from .paint import COURT, COURT_LIT, GLASS, INK, INK_DIM, NIGHT, SIGN, WIDTH, as_png, font
from .wording import FORMAT_LABEL, plural

if TYPE_CHECKING:
    from collections.abc import Sequence

    from padel_tour.services import StandingView, TournamentView

PODIUM = 3

TITLE_TOP = 46
PODIUM_TOP = 200
#: Heights of the first, second and third blocks. The winner's is tallest, which is the
#: whole idea of drawing a podium rather than writing a list.
BLOCK = {1: 250, 2: 190, 3: 150}
BLOCK_WIDTH = 250
BLOCK_GAP = 18
PODIUM_FLOOR = PODIUM_TOP + max(BLOCK.values())

ROW = 46
LIST_TOP = PODIUM_FLOOR + 56
BOTTOM = 44

#: Second, first, third — the order they stand in, not the order they finished.
ARRANGEMENT = (2, 1, 3)

#: Numerals, not medal emoji. Golos Text has no emoji glyphs and Pillow does not fall back
#: to a colour font, so 🥇 comes out as an empty box — which is worse than a plain 1.
BLOCK_COLOUR = {1: SIGN, 2: "#A7C0D6", 3: "#C08552"}


def render(view: TournamentView) -> bytes | None:
    """The final card, or ``None`` if nobody has finished anything worth celebrating."""
    table = view.standings
    if not table or not any(row.played for row in table):
        return None

    rest = table[PODIUM:]
    height = (LIST_TOP + ROW * len(rest) + BOTTOM) if rest else (PODIUM_FLOOR + BOTTOM)

    image = Image.new("RGB", (WIDTH, height), NIGHT)
    draw = ImageDraw.Draw(image)

    _title(draw, view)
    _podium(draw, table)
    _rest(draw, rest)

    return as_png(image)


def _title(draw: ImageDraw.ImageDraw, view: TournamentView) -> None:
    """The headline says what this was, not who won.

    The winner's name is on the tallest block a centimetre below; printing it twice makes
    the card about one person, which is the thing the podium is there to avoid.
    """
    draw.text(
        (WIDTH // 2, TITLE_TOP), "ТУРНИР ЗАВЕРШЁН", font=font(34, "Bold"), fill=GLASS, anchor="mm"
    )
    people = len(view.standings)
    subtitle = (
        f"{FORMAT_LABEL[view.format]} · {people} {plural(people, 'игрок', 'игрока', 'игроков')}"
        f" · до {view.points_per_match}"
    )
    draw.text(
        (WIDTH // 2, TITLE_TOP + 44), subtitle, font=font(26, "Medium"), fill=INK_DIM, anchor="mm"
    )


def _podium(draw: ImageDraw.ImageDraw, rows: Sequence[StandingView]) -> None:
    """Three blocks, second-first-third, standing on a common floor."""
    span = BLOCK_WIDTH * len(ARRANGEMENT) + BLOCK_GAP * (len(ARRANGEMENT) - 1)
    left = (WIDTH - span) // 2

    for slot, place in enumerate(ARRANGEMENT):
        x0 = left + slot * (BLOCK_WIDTH + BLOCK_GAP)
        x1 = x0 + BLOCK_WIDTH
        if place > len(rows):
            continue
        row = rows[place - 1]

        top = PODIUM_FLOOR - BLOCK[place]
        draw.rounded_rectangle(
            [x0, top, x1, PODIUM_FLOOR], radius=6, fill=COURT if place != 1 else COURT_LIT
        )
        draw.rounded_rectangle([x0, top, x1, top + 6], radius=3, fill=BLOCK_COLOUR[place])

        middle = (x0 + x1) // 2
        draw.text(
            (middle, top - 32),
            str(place),
            font=font(34, "ExtraBold"),
            fill=BLOCK_COLOUR[place],
            anchor="mm",
        )
        draw.text((middle, top + 46), row.name, font=font(32, "Bold"), fill=INK, anchor="mm")
        draw.text(
            (middle, top + 88),
            str(row.points_for),
            font=font(40, "ExtraBold"),
            fill=GLASS,
            anchor="mm",
        )
        draw.text(
            (middle, top + 128),
            f"{row.diff:+d}",
            font=font(24, "Medium"),
            fill=INK_DIM,
            anchor="mm",
        )


def _rest(draw: ImageDraw.ImageDraw, rows: Sequence[StandingView]) -> None:
    """Everyone off the podium, named. Being fourth is not the same as not being there."""
    for index, row in enumerate(rows):
        y = LIST_TOP + index * ROW
        draw.text((120, y), f"{row.rank}", font=font(26, "Medium"), fill=INK_DIM, anchor="rm")
        draw.text((150, y), row.name, font=font(28), fill=INK, anchor="lm")
        draw.text(
            (WIDTH - 200, y), str(row.points_for), font=font(28, "Bold"), fill=INK, anchor="rm"
        )
        draw.text(
            (WIDTH - 120, y), f"{row.diff:+d}", font=font(24, "Medium"), fill=INK_DIM, anchor="rm"
        )


__all__ = ["render"]
