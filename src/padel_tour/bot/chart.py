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
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

from .paint import COURT, INK_FAINT, NIGHT, WIDTH, as_png, font, lane

if TYPE_CHECKING:
    from collections.abc import Callable

    from padel_tour.services import TournamentView

ROW = 54
TOP = 70
BOTTOM = 46
LEFT = 54
#: Room on the right for the name at the end of each line, which is where the eye lands.
RIGHT = 260

DOT = 6
LINE = 5


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
        colour = lane(index)
        path = [(x(point.round_no), y(point.rank)) for point in points]
        if len(path) > 1:
            draw.line(path, fill=colour, width=LINE, joint="curve")
        for spot in path:
            draw.ellipse([spot[0] - DOT, spot[1] - DOT, spot[0] + DOT, spot[1] + DOT], fill=colour)
        last = path[-1]
        draw.text(
            (last[0] + 18, last[1]),
            f"{points[-1].rank}. {name}",
            font=font(26),
            fill=colour,
            anchor="lm",
        )

    return as_png(image)


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
            (at, TOP - 46), f"R{round_no}", font=font(22, "Medium"), fill=INK_FAINT, anchor="mm"
        )

    for place in range(1, places + 1):
        draw.text(
            (LEFT - 26, y(place)),
            str(place),
            font=font(22, "Medium"),
            fill=INK_FAINT,
            anchor="rm",
        )


__all__ = ["render"]
