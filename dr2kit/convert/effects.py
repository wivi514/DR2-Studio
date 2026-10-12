"""Change a particle effect: recolour, resize, retime, swap its picture (phase 13 step 6).

Why: the user wants "more tools for modders to add their own FX", with the game's
effects as the easy start: take an effect (the Flaming Sword's flame along the blade),
make it icy blue, put it on a weapon. An effect is a list of emitters
(`formats.effect`); this module applies **changes** to one, described as plain data so
a mod can hold the changes instead of the game's bytes (LICENSE):

```json
{"layout": [1, 1, 3],      // the new emitter list: base emitters by number, copied (first)
 "hue": 200,               // turn every colour to this hue (0-360°: 0 red, 120 green, 200 ice blue)
 "saturation": 1.2,        // × the colours' saturation
 "brightness": 1.1,        // × their brightness
 "alpha": 0.8,             // × their opacity
 "size": 1.5,              // × every size key
 "time": 0.5,              // × the colour key times (shorter life ❓)
 "texture": {"fire_flame": "glow"},   // swap pictures, by name (effects.tex)
 "emitters": {"1": {"gravity": [0, 2, 0]}},   // any field of one emitter (by number)
 "remove": [3]}            // emitters to drop
```

``layout`` (phase 13 step 6.5) builds an effect with more or fewer emitters than its
base: each number is one of the base's emitters, copied; the other keys then apply to
the new list (``"emitters": {"2": …}`` is the third of the new list).

`apply_changes` does it on an `Effect`; `describe` says what an effect is made of in
words. Keys are applied in that order; unknown keys are an error (a typo must not be
ignored). Colours change in HSV so a fire stays a fire's shape of light: dark smoke stays
dark, only hues turn. Grey keys (no saturation) take the new hue only with
``"saturation"`` above 1 ❓ (kept grey by default).
"""

from __future__ import annotations

import colorsys

from ..errors import Dr2Error
from ..formats.effect import BY_NAME, SHAPE_NAMES, Effect, Emitter

KEYS = ("layout", "hue", "saturation", "brightness", "alpha", "size", "time", "texture", "emitters",
        "remove")
GREY = 0.05                      # a key this little saturated counts as grey


def _recolour(rgba, hue: float | None, sat: float, val: float, alpha: float):
    r, g, b, a = rgba
    h, s, v = colorsys.rgb_to_hsv(max(r, 0.0), max(g, 0.0), max(b, 0.0))
    if hue is not None and (s > GREY or sat > 1.0):
        h = (hue % 360.0) / 360.0
        if s <= GREY:
            s = min(1.0, 0.25 * sat)
    s = min(1.0, s * sat)
    v = min(1.0, v * val)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (r, g, b, min(1.0, a * alpha))


def apply_changes(fx: Effect, changes: dict, where: str = "") -> Effect:
    """``fx`` with ``changes`` applied (module docstring); changes it in place too."""
    pre = f"{where}: " if where else ""
    bad = [k for k in changes if k not in KEYS]
    if bad:
        raise Dr2Error(f"{pre}unknown change(s) {', '.join(bad)} (known: {', '.join(KEYS)})")
    if "layout" in changes:
        base = list(fx.emitters)
        try:
            fx.emitters = [Emitter(bytearray(base[int(i)].raw)) for i in changes["layout"]]
        except (ValueError, IndexError, TypeError):
            raise Dr2Error(f"{pre}layout {changes['layout']!r}: emitter numbers of the base, "
                           f"0-{len(base) - 1}") from None
        if not fx.emitters:
            raise Dr2Error(f"{pre}layout: an effect needs at least one emitter")
    hue = changes.get("hue")
    sat = float(changes.get("saturation", 1.0))
    val = float(changes.get("brightness", 1.0))
    alpha = float(changes.get("alpha", 1.0))
    if hue is not None or sat != 1.0 or val != 1.0 or alpha != 1.0:
        for e in fx.emitters:
            e.set_colour_keys([_recolour(k, hue, sat, val, alpha) for k in e.colour_keys()])
    if "size" in changes:
        k = float(changes["size"])
        for e in fx.emitters:
            e.set("sizes", [v * k for v in e.get("sizes")])
    if "time" in changes:
        k = float(changes["time"])
        for e in fx.emitters:
            e.set("colour_times", [v * k for v in e.get("colour_times")])
    for old, new in (changes.get("texture") or {}).items():
        hit = False
        for e in fx.emitters:
            if e.texture.lower() == old.lower():
                e.texture = new
                hit = True
        if not hit:
            raise Dr2Error(f"{pre}no emitter uses the picture {old!r} "
                           f"(it has {', '.join(sorted({e.texture for e in fx.emitters}))})")
    for num, fields in (changes.get("emitters") or {}).items():
        try:
            e = fx.emitters[int(num)]
        except (ValueError, IndexError):
            raise Dr2Error(f"{pre}emitter {num}: the effect has emitters 0-"
                           f"{len(fx.emitters) - 1}") from None
        for key, value in fields.items():
            if key == "texture":
                e.texture = value
            elif key == "shape_values":
                e.shape_values = value
            elif key in BY_NAME:
                e.set(key, value)
            else:
                raise Dr2Error(f"{pre}emitter {num}: no field {key!r}")
    drop = sorted({int(i) for i in changes.get("remove") or []}, reverse=True)
    for i in drop:
        if not 0 <= i < len(fx.emitters):
            raise Dr2Error(f"{pre}remove {i}: the effect has emitters 0-{len(fx.emitters) - 1}")
        del fx.emitters[i]
    if not fx.emitters:
        raise Dr2Error(f"{pre}an effect needs at least one emitter")
    return fx


def _hex(rgba) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in rgba[:3])


def describe(fx: Effect) -> list[str]:
    """What an effect is made of, one line per emitter (for lists and the CLI)."""
    lines = []
    for i, e in enumerate(fx.emitters):
        keys = e.colour_keys()
        cols = " → ".join(f"{_hex(k)}@{k[3]:.2f}" for k in keys if k[3] > 0.004) or "clear"
        sizes = e.get("sizes")
        lines.append(f"{i}: {e.texture} ({SHAPE_NAMES[e.get('shape')]}), colours {cols}, "
                     f"size {min(sizes):.3g}-{max(sizes):.3g} m, over "
                     f"{max(e.get('colour_times')):.2f} s")
    return lines


def main_colour(fx: Effect) -> tuple[float, float, float]:
    """The effect's brightest, most opaque colour (for swatches)."""
    best, score = (0.5, 0.5, 0.5), -1.0
    for e in fx.emitters:
        for r, g, b, a in e.colour_keys():
            s = a * (max(r, g, b) + 0.5 * (max(r, g, b) - min(r, g, b)))
            if s > score:
                best, score = (r, g, b), s
    return best
