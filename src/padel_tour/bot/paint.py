"""Shared ink for the pictures the bot draws.

Two things are drawn — the climb and the final card — and they have to look like the same
product, which means one palette and one typeface rather than two that drift.

The font ships in the repository. Pillow carries none, whatever is installed on the platform
is not ours to predict, and every name here is Cyrillic. Golos Text is the face the web uses,
so a picture in a chat and a page in a browser are recognisably the same thing.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageFont

FONT_PATH = Path(__file__).parent / "assets" / "GolosText.ttf"

#: The web's own variables, copied rather than imported — nothing in Python should have to
#: read a stylesheet, and these change about once a year.
NIGHT = "#071A1F"
COURT = "#0E4C5C"
COURT_LIT = "#12667A"
GLASS = "#7FD4C8"
SIGN = "#FFB454"
INK = "#E8F4F2"
INK_DIM = "#9CBCC0"
INK_FAINT = "#5E8189"

#: Straight from the web's `LANE_COLOURS`, so a group that looks at both sees one product.
#:
#: High chroma on purpose. Against a near-black court a muted set reads as one grey tangle
#: once there are eight lines on it, and the hues are ordered so neighbouring places do not
#: get neighbouring colours — two lines crossing is exactly when telling them apart matters.
LANES = (
    "#3FF5D4",
    "#FFAE2B",
    "#6EA8FF",
    "#FF6FD8",
    "#B6FF3D",
    "#FF5E5B",
    "#31E1FF",
    "#B388FF",
    "#FFD93D",
    "#4DFF9E",
    "#FF8A3D",
    "#8AA9FF",
)

#: Telegram scales a photo to the chat width, so this is about how much detail survives
#: rather than how big it looks.
WIDTH = 1000


@lru_cache(maxsize=16)
def font(size: int, weight: str = "SemiBold") -> ImageFont.FreeTypeFont:
    """One face, several weights.

    Cached because a single picture draws a dozen labels and parsing the file each time
    would dominate the render. A variable font, so weight is an axis rather than a file.
    """
    face = ImageFont.truetype(FONT_PATH, size)
    face.set_variation_by_name(weight)
    return face


def lane(index: int) -> str:
    """A colour per player. Wraps rather than running out — a group can be any size."""
    return LANES[index % len(LANES)]


def as_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


__all__ = [
    "COURT",
    "COURT_LIT",
    "FONT_PATH",
    "GLASS",
    "INK",
    "INK_DIM",
    "INK_FAINT",
    "LANES",
    "NIGHT",
    "SIGN",
    "WIDTH",
    "as_png",
    "font",
    "lane",
]
