"""Pictures of a weapon made from its model: the inventory icon and the combo card (phase 13).

Why: the user asked that "the icon in the inventory should be a picture of the 3D
object". The game's icons are pictures too: a weapon pack's ``w_<name>.bct`` (128×64
DXT1, see-through background) shows the weapon lying on a slant, handle at the left, seen
on its flat side, with a thin dark outline (decoded and compared: ``w_broadsword``,
``w_leadpipe``, ``w_sledgehammer``…, docs/formats.md §Weapons). `weapon_icon` draws one
the same way with the toolkit's software renderer (`convert.render`): the camera looks at
the weapon's flat side (`convert.weapon_fit.Frame.thin`), the weapon's line is turned to
``ANGLE`` degrees below the horizontal, the picture is framed on it, and `outline` adds the
dark edge.

Combo cards (`data/frontend/combocards.tex/comboc_<name>.bct`, 364×512 DXT1): a portrait
window at the top (Chuck holding the weapon on the game's cards), a corner arrow and
"X2 PP!" drawn over it, and below, line drawings of the two items that make it, around a
"+" (`CARD`, measured on ``comboc_spikedbat``). `card_template` makes the empty card: the
per-pixel median of all the game's cards (they share the frame, arrow, "X2 PP!", panel and
"+"; their pictures differ, so the median keeps the shared parts). `card_portrait` renders
the weapon for the window on a glow; `item_drawing` draws an item as lines on clear
(silhouette and creases, like the cards' drawings); `compose_card` puts them on the empty
card, and `faded` gives the portrait of the "not found yet" copy (``comboc_<name>_no``,
made on the empty ``_no`` card). The mod holds only the modder's own pictures
and a recipe; the game card and the ingredients' drawings are made from the player's game
when the mod is built (`mods.newitem.build_copy`, LICENSE).

Needs numpy.
"""

from __future__ import annotations

import math

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

from ..errors import Dr2Error

ICON_SIZE = (128, 64)
ANGLE = 23.0                      # degrees below the horizontal (w_broadsword: ~23)
OUTLINE = (14, 14, 14)

# combo card regions (x0, y0, x1, y1), measured on the spread between all of a game's
# cards (`card_template`): CZ's 51 and CW's 66 agree
CARD_SIZE = (364, 512)
CARD = {
    "window": (26, 337, 40, 26, 287, 266),     # x0, x1, top y at x0 / x1, bottom y at x0 / x1
    "keep": [(19, 15, 62, 60), (236, 14, 350, 58)],   # the corner arrow, "X2 PP!"
    "left": (35, 361, 166, 483),               # the first item's drawing
    "right": (199, 361, 332, 483),             # the second item's
}
GLOW = {                                       # portrait backgrounds by element
    "none": ((120, 24, 28), (235, 110, 110)),
    "fire": ((110, 20, 0), (255, 170, 60)),
    "freeze": ((10, 30, 80), (150, 210, 255)),
    "shock": ((40, 30, 0), (255, 240, 120)),
}


def _need_numpy() -> None:
    if np is None:
        raise Dr2Error("drawing pictures of models needs numpy (pip install numpy)")


def weapon_basis(frame, angle: float = ANGLE, flip: bool = False):
    """(right, up, toward camera) so the weapon's line runs ``angle`` degrees below the
    horizontal, handle at the left, its flat side to the camera."""
    a = math.radians(angle)
    axis, side = np.asarray(frame.axis, float), np.asarray(frame.side, float)
    if flip:
        side = -side
    right = math.cos(a) * axis + math.sin(a) * side
    up = -math.sin(a) * axis + math.cos(a) * side
    d = np.cross(right, up)
    return right, up, d


def outline(img: "np.ndarray", colour=OUTLINE, px: int = 1) -> "np.ndarray":
    """``img`` (RGBA uint8) with a ``px``-wide edge of ``colour`` around what it shows."""
    _need_numpy()
    a = img[..., 3] > 127
    grown = a.copy()
    for _ in range(px):
        g = grown.copy()
        g[1:] |= grown[:-1]
        g[:-1] |= grown[1:]
        g[:, 1:] |= grown[:, :-1]
        g[:, :-1] |= grown[:, 1:]
        grown = g
    out = img.copy()
    edge = grown & ~a
    out[edge, :3] = colour
    out[edge, 3] = 255
    return out


def _contrast(img: "np.ndarray", gain: float = 1.15) -> "np.ndarray":
    rgb = img[..., :3].astype(np.float32)
    mean = rgb[img[..., 3] > 0].mean(axis=0) if (img[..., 3] > 0).any() else 128
    rgb = (rgb - mean) * gain + mean
    out = img.copy()
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return out


def weapon_icon(parts, frame, size=ICON_SIZE, angle: float = ANGLE,
                flip: bool = False) -> "np.ndarray":
    """The inventory icon (RGBA, ``size`` = (width, height)) of a weapon's renderer
    ``parts`` (`convert.render.scene_parts`) laid on its line ``frame``."""
    _need_numpy()
    from .render import render
    w, h = size
    img = render(parts, width=w, height=h, basis=weapon_basis(frame, angle, flip), fill=0.9)
    if img is None:
        raise Dr2Error("the model has nothing to draw")
    img[..., 3] = np.where(img[..., 3] >= 128, 255, 0)      # DXT1: on or off
    return outline(_contrast(img))


# --- combo cards ------------------------------------------------------------------------

def _glow(w: int, h: int, colours) -> "np.ndarray":
    inner, outer = (np.array(c, np.float32) for c in (colours[1], colours[0]))
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot((x - w * 0.55) / (w * 0.6), (y - h * 0.45) / (h * 0.6))
    t = np.clip(r, 0, 1)[..., None] ** 1.3
    rgb = inner * (1 - t) + outer * t
    return np.concatenate([rgb, np.full((h, w, 1), 255, np.float32)], axis=2).astype(np.uint8)


def card_portrait(parts, frame, element: str = "none", flip: bool = False,
                  glow: bool = True) -> "np.ndarray":
    """The card's portrait (RGBA, opaque, `portrait_size`): the weapon raised on a slant
    over a glow in the element's colours (``glow=False``: on a clear background, for
    `faded`: the card shows through)."""
    _need_numpy()
    from .render import render
    w, h = portrait_size()
    bg = _glow(w, h, GLOW.get(element, GLOW["none"])) if glow else np.zeros((h, w, 4), np.uint8)
    img = render(parts, width=w, height=h, basis=weapon_basis(frame, -48.0, flip), fill=0.88)
    if img is None:
        raise Dr2Error("the model has nothing to draw")
    img = outline(_contrast(img, 1.2), px=2)
    if not glow:
        return img
    _paste(bg, img, 0, 0)
    return bg


def item_drawing(parts, size=(134, 118)) -> "np.ndarray":
    """An item as the cards draw their ingredients: black lines (its outline and its
    creases) on a clear background, RGBA ``size`` = (width, height)."""
    _need_numpy()
    from .render import render
    w, h = size
    img = render(parts, width=w * 2, height=h * 2, fill=0.9)
    if img is None:
        return np.zeros((h, w, 4), np.uint8)
    a = img[..., 3] > 127
    lum = img[..., :3].astype(np.float32).mean(axis=2)
    edge = np.zeros_like(a)
    edge[1:-1, 1:-1] = a[1:-1, 1:-1] & ~(a[:-2, 1:-1] & a[2:, 1:-1] & a[1:-1, :-2] & a[1:-1, 2:])
    gx = np.zeros_like(lum)
    gy = np.zeros_like(lum)
    gx[:, 1:-1] = lum[:, 2:] - lum[:, :-2]
    gy[1:-1] = lum[2:] - lum[:-2]
    crease = (np.hypot(gx, gy) > 70) & a
    line = edge | crease
    thick = line.copy()                                   # 2 px at double size = 1 px
    thick[1:] |= line[:-1]
    thick[:, 1:] |= line[:, :-1]
    big = np.zeros((h * 2, w * 2, 4), np.uint8)
    big[thick, 3] = 255
    out = big.reshape(h, 2, w, 2, 4).astype(np.float32).mean(axis=(1, 3))
    out[..., 3] = np.clip(out[..., 3] * 1.6, 0, 255)
    return out.astype(np.uint8)


def _paste(dst: "np.ndarray", src: "np.ndarray", x: int, y: int) -> None:
    h, w = src.shape[:2]
    region = dst[y:y + h, x:x + w]
    a = src[..., 3:4].astype(np.float32) / 255
    region[..., :3] = (src[..., :3] * a + region[..., :3] * (1 - a)).astype(np.uint8)


def card_template(cards: list) -> "np.ndarray":
    """The empty card: the per-pixel median of a game's cards (RGBA 364×512 each). Every
    card shares the frame, the corner arrow, "X2 PP!", the drawing panel and its "+";
    the pictures differ, so the median keeps the shared parts and blurs the rest away
    (the portrait window then gets the new picture, the panel the new drawings)."""
    _need_numpy()
    cards = [c for c in cards if c.shape[:2] == (CARD_SIZE[1], CARD_SIZE[0])]
    if not cards:
        raise Dr2Error("no combo card to make an empty card from")
    return np.median(np.stack(cards), axis=0).astype(np.uint8)


def window_mask() -> "np.ndarray":
    """The portrait window (a slanted four-sided shape) as a boolean mask of the card."""
    x0, x1, t0, t1, b0, b1 = CARD["window"]
    h, w = CARD_SIZE[1], CARD_SIZE[0]
    y, x = np.mgrid[0:h, 0:w]
    f = (x - x0) / (x1 - x0)
    return (x >= x0) & (x <= x1) & (y >= t0 + (t1 - t0) * f) & (y <= b0 + (b1 - b0) * f)


def portrait_size() -> tuple[int, int]:
    """(width, height) of the picture `compose_card` puts in the window."""
    x0, x1, t0, t1, b0, b1 = CARD["window"]
    return x1 - x0 + 1, max(b0, b1) - min(t0, t1) + 1


def compose_card(empty: "np.ndarray", portrait: "np.ndarray | None" = None,
                 drawings: "list | None" = None, line=(0, 0, 0)) -> "np.ndarray":
    """A combo card (RGBA 364×512): the empty card (`card_template`) with ``portrait``
    (`portrait_size`) in its window and the two item drawings (`item_drawing`, or None)
    on its panel, their lines in ``line``."""
    _need_numpy()
    if empty.shape[:2] != (CARD_SIZE[1], CARD_SIZE[0]):
        raise Dr2Error(f"a combo card is {CARD_SIZE[0]}×{CARD_SIZE[1]}, this picture "
                       f"{empty.shape[1]}×{empty.shape[0]}")
    out = empty.copy()
    if portrait is not None:
        x0, x1, t0, t1, *_ = CARD["window"]
        w, h = portrait_size()
        if portrait.shape[:2] != (h, w):
            raise Dr2Error(f"the card's picture must be {w}×{h}")
        top = min(t0, t1)
        full = empty.copy()
        _paste(full, portrait, x0, top)                  # a clear background shows the card
        m = window_mask()
        ax0, ay0, ax1, ay1 = CARD["keep"][0]             # the arrow square stays whole
        m[ay0:ay1, ax0:ax1] = False
        for bx0, by0, bx1, by1 in CARD["keep"][1:]:      # "X2 PP!": its letters stay on top
            e = empty[by0:by1, bx0:bx1].astype(np.int32)
            yellow = (e[..., 0] > 150) & (e[..., 1] > 120) & (e[..., 2] < 110)
            near = yellow.copy()
            for _ in range(3):                           # with their black edge
                g = near.copy()
                g[1:] |= near[:-1]
                g[:-1] |= near[1:]
                g[:, 1:] |= near[:, :-1]
                g[:, :-1] |= near[:, 1:]
                near = g
            m[by0:by1, bx0:bx1] &= ~near
        out[m] = full[m]
    for key, pic in zip(("left", "right"), drawings or ()):
        if pic is None:
            continue
        x0, y0, x1, y1 = CARD[key]
        pic = pic[:y1 - y0, :x1 - x0].copy()
        pic[..., :3] = line
        dh, dw = pic.shape[:2]
        _paste(out, pic, x0 + (x1 - x0 - dw) // 2, y0 + (y1 - y0 - dh) // 2)
    out[..., 3] = 255
    return out


def faded(portrait: "np.ndarray") -> "np.ndarray":
    """A portrait in the "not found yet" style of the game's ``_no`` cards: pale on the
    card's dark red, like a worn print."""
    _need_numpy()
    lum = portrait[..., :3].astype(np.float32) @ np.array([0.3, 0.55, 0.15], np.float32) / 255
    lum = np.clip((lum - 0.2) * 1.6, 0, 1) ** 0.8
    dark, light = np.array([110, 30, 40], np.float32), np.array([236, 208, 208], np.float32)
    out = portrait.copy()
    out[..., :3] = (dark * (1 - lum[..., None]) + light * lum[..., None]).astype(np.uint8)
    return out
