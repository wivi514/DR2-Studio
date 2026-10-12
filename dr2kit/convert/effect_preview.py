"""An approximate picture of a particle effect, drawn from its emitters (phase 13 step 6.3).

Why: choosing an effect by name ("snowtrail_wpn_bs_1") or recolouring one blind is hard;
a picture shows what changed. The game's particle system isn't emulated: this is a
**sketch** from what the emitter data says for sure (`formats.effect`, status ``ok``):
the particle picture (``data/models/effects.tex``), the five colour keys with their
times, the five size keys and the spawn shape, plus the fields read only from their
values (``speed``, ``gravity``, ``spread``: "?" in `formats.effect.FIELDS`). Each
emitter's particles are born along its shape over its life, move by its speed and
gravity, and are drawn as their picture, tinted by the colour key of their age, sized
by the size key, added on top of each other (as fire and glows are drawn) on a dark
background. The view is from the side (x right, y up), the effect's origin at the
middle bottom third.

Measured against the game: the Flaming Sword's flame recoloured green showed green in
game (headless CZ, 2026-10-12); shapes and motion are not compared yet.

Needs numpy.
"""

from __future__ import annotations

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

SIZE = 256
PARTICLES = 48                  # per emitter
VIEW = 1.6                      # metres across the picture (grown to fit the effect)


def _key(values, times, t):
    """A key curve's value at time ``t`` (five keys: t0 = 0, then ``times``)."""
    ts = [0.0] + list(times)
    if t <= ts[0]:
        return values[0]
    for i in range(1, len(ts)):
        if t <= ts[i]:
            f = (t - ts[i - 1]) / max(ts[i] - ts[i - 1], 1e-6)
            a, b = values[i - 1], values[i]
            return a + (b - a) * f if not isinstance(a, tuple) else \
                tuple(x + (y - x) * f for x, y in zip(a, b))
    return values[-1]


def _sprite(texture, px: int):
    """The particle picture at ``px``×``px`` (nearest), float RGBA; a soft dot without."""
    px = max(2, px)
    if texture is None:
        y, x = np.mgrid[0:px, 0:px].astype(np.float32)
        r = np.hypot(x - px / 2 + 0.5, y - px / 2 + 0.5) / (px / 2)
        a = np.clip(1 - r, 0, 1) ** 1.5
        return np.dstack([np.ones((px, px, 3), np.float32), a])
    h, w = texture.shape[:2]
    ys = (np.arange(px) * h // px).clip(0, h - 1)
    xs = (np.arange(px) * w // px).clip(0, w - 1)
    return texture[ys][:, xs]


def preview(effect, textures=None, size: int = SIZE, seed: int = 1):
    """An RGBA picture (uint8, ``size``²) of ``effect`` (`formats.effect.Effect`).
    ``textures(name)`` gives a particle picture as float RGBA (h, w, 4), or None."""
    if np is None:
        raise RuntimeError("the effect preview needs numpy")
    rng = np.random.default_rng(seed)
    parts = []                                       # (x, y, size m, rgba, texture name)
    for m in effect.emitters:
        times = m.get("colour_times")
        life = max(max(times), 0.05)
        cols = m.colour_keys()
        sizes = m.get("sizes")
        speed = np.array(m.get("speed"), dtype=np.float64)
        gravity = np.array(m.get("gravity"), dtype=np.float64)
        spread = np.array(m.get("spread"), dtype=np.float64)
        shape = m.get("shape")
        sv = m.shape_values
        for k in range(PARTICLES):
            age = life * (k + rng.random()) / PARTICLES
            if shape in (1, 2) and len(sv) == 6:      # a box from the second corner to the first
                a, b = np.array(sv[3:6]), np.array(sv[0:3])
                start = a + (b - a) * rng.random(3)
            elif shape == 3 and sv:
                d = rng.normal(size=3)
                start = d / max(np.linalg.norm(d), 1e-9) * abs(sv[-1]) * rng.random()
            else:
                start = np.zeros(3)
            start = start + np.array(m.get("offset")) + spread * (rng.random(3) - 0.5)
            jitter = 1 + 0.3 * (rng.random(3) - 0.5)
            pos = start + speed * jitter * age + 0.5 * gravity * age * age
            rgba = _key(cols, times, age)
            s = float(_key(sizes, times, age))
            if rgba[3] > 0.003 and s > 0:
                parts.append((pos[0], pos[1], s, rgba, m.texture))
    img = np.zeros((size, size, 3), np.float32)
    img[...] = (0.07, 0.07, 0.09)
    if not parts:
        return _to_u8(img)
    xs = np.array([p[0] for p in parts])
    ys = np.array([p[1] for p in parts])
    ss = np.array([p[2] for p in parts])
    span = max(VIEW, float(np.ptp(xs) + ss.max() * 2), float(np.ptp(ys) + ss.max() * 2))
    scale = size / span
    cx = (xs.min() + xs.max()) / 2
    base = ys.min() - ss.max()
    cache: dict = {}
    for x, y, s, rgba, tex in parts:
        px = int(round(s * 2 * scale))
        if px < 1 or px > size * 2:
            continue
        key = (tex, px)
        if key not in cache:
            cache[key] = _sprite(textures(tex) if textures else None, px)
        spr = cache[key]
        col = np.array(rgba[:3], np.float32)
        a = spr[..., 3:4] * float(rgba[3])
        u = int(round((x - cx) * scale + size / 2 - px / 2))
        v = int(round(size - (y - base) * scale - size * 0.15 - px / 2))
        x0, y0 = max(u, 0), max(v, 0)
        x1, y1 = min(u + px, size), min(v + px, size)
        if x0 >= x1 or y0 >= y1:
            continue
        sub = spr[y0 - v:y1 - v, x0 - u:x1 - u, :3] * col * a[y0 - v:y1 - v, x0 - u:x1 - u]
        img[y0:y1, x0:x1] += sub                     # added, as glows and flames are
    return _to_u8(img)


def _to_u8(img):
    out = np.zeros(img.shape[:2] + (4,), np.uint8)
    out[..., :3] = np.clip(img * 255, 0, 255).astype(np.uint8)
    out[..., 3] = 255
    return out


def texture_finder(tree):
    """``textures(name)`` for `preview`: the particle pictures of ``effects.tex``."""
    from ..formats.bct import Bct
    from .texture import to_image
    arc = tree.open_archive(tree.resolve("data/models/effects.tex").vpath)
    by = {e.name.lower().removesuffix(".bct"): e for e in arc.entries}
    cache: dict = {}

    def find(name):
        key = name.lower()
        if key not in cache:
            e = by.get(key)
            if e is None:
                cache[key] = None
            else:
                im = to_image(Bct.parse(e.data(), e.name))
                cache[key] = np.frombuffer(im.rgba, np.uint8).reshape(
                    im.height, im.width, 4).astype(np.float32) / 255
        return cache[key]
    return find


