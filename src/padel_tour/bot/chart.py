"""Drawing the tournament as a picture.

What the bot showed before was a table of cumulative points with a rank path spelled out as
``3→2→2→1``. Nothing about it was a chart: there was no geometry, so there was nothing to
read at a glance, which is the only reason to draw one.

**Places, not points.** Points only ever go up, and eight nearly parallel climbing lines say
almost nothing. Place moves both ways, and the question people actually ask a tournament
chart is "when did I drop".

**Pillow, not matplotlib.** In production the bot is served by the same serverless function
as the API. matplotlib and numpy are tens of megabytes in that bundle for one screen; Pillow
is a few, and drawing lines between points we already have is not the hard part.

**The font ships with us.** Pillow carries no fonts, whatever is installed on the platform
is not ours to predict, and every name here is Cyrillic. Golos Text is the same face the web
uses, so the picture looks like the product rather than like a plotting library.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from collections.abc import Callable

    from padel_tour.services import TournamentView

FONT_PATH = Path(__file__).parent / "assets" / "GolosText.ttf"

#: Telegram scales a photo to the chat width, so this is about how much detail survives
#: rather than about how big it looks. Wide enough for a dozen rounds, short enough that a
#: phone shows it without the caption scrolling away.
WIDTH = 1000
ROW = 54
TOP = 70
BOTTOM = 46
LEFT = 54
#: Room on the right for the name at the end of each line, which is where the eye lands.
RIGHT = 260

#: Straight from the web's `LANE_COLOURS`, so a group that looks at both sees one product.
LANES = (
    "#7FD4C8",
    "#FFB454",
    "#8FB8FF",
    "#F2A5C4",
    "#B9E36A",
    "#E8F4F2",
    "#63C6E8",
    "#C6A6F0",
    "#FF9E7A",
    "#9AD6A0",
    "#D8C77E",
    "#A7C0D6",
)

NIGHT = "#071A1F"
COURT = "#0E4C5C"
INK_FAINT = "#5E8189"
INK = "#E8F4F2"

DOT = 6
LINE = 5


@lru_cache(maxsize=8)
def _font(size: int, weight: str = "SemiBold") -> ImageFont.FreeTypeFont:
    """One face, several weights.

    Cached because a tournament screen draws a dozen labels and parsing the file each time
    would dominate the render. Variable font, so the weight is an axis rather than a file.
    """
    face = ImageFont.truetype(FONT_PATH, size)
    face.set_variation_by_name(weight)
    return face


def _lane(index: int) -> str:
    return LANES[index % len(LANES)]


def render(view: TournamentView) -> bytes | None:
    """The tournament as a PNG, or ``None`` if nothing has been played yet.

    Answering ``None`` rather than an empty chart is deliberate: a picture of nothing is
    worse than the round screen, which at least says who is about to play whom.
    """
    series = view.progression
    played = [point.round_no for point in next(iter(series.values()), ())]
    if not played:
        return None

    lines = [(row.name, series[row.player_id]) for row in view.standings]
    height = TOP + ROW * max(len(lines) - 1, 1) + BOTTOM

    image = Image.new("RGB", (WIDTH, height), NIGHT)
    draw = ImageDraw.Draw(image)

    span = WIDTH - LEFT - RIGHT
    step = span / max(len(played) - 1, 1)

    def x(round_no: int) -> float:
        return LEFT + played.index(round_no) * step

    def y(rank: int) -> float:
        return TOP + (rank - 1) * ROW

    _draw_grid(draw, played, len(lines), x, y)

    # Drawn in reverse so the leader's line ends up on top of everyone else's.
    for index, (name, points) in reversed(list(enumerate(lines))):
        colour = _lane(index)
        path = [(x(point.round_no), y(point.rank)) for point in points]
        if len(path) > 1:
            draw.line(path, fill=colour, width=LINE, joint="curve")
        for spot in path:
            draw.ellipse([spot[0] - DOT, spot[1] - DOT, spot[0] + DOT, spot[1] + DOT], fill=colour)
        last = path[-1]
        draw.text(
            (last[0] + 18, last[1]),
            f"{points[-1].rank}. {name}",
            font=_font(26),
            fill=colour,
            anchor="lm",
        )

    return _as_png(image)


def _draw_grid(
    draw: ImageDraw.ImageDraw,
    played: list[int],
    places: int,
    x: Callable[[int], float],
    y: Callable[[int], float],
) -> None:
    """Round markers along the top, place numbers down the side.

    Faint on purpose. The grid is there to be measured against when a line looks odd, not
    to be read on its own.
    """
    bottom = y(places)
    for round_no in played:
        at = x(round_no)
        draw.line([(at, TOP - 30), (at, bottom + 22)], fill=COURT, width=2)
        draw.text(
            (at, TOP - 46), f"R{round_no}", font=_font(22, "Medium"), fill=INK_FAINT, anchor="mm"
        )

    for place in range(1, places + 1):
        draw.text(
            (LEFT - 26, y(place)),
            str(place),
            font=_font(22, "Medium"),
            fill=INK_FAINT,
            anchor="rm",
        )


def _as_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


__all__ = ["render"]
