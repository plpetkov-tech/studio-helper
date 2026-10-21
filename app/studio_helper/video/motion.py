"""How things move: easing curves and animations named like Figma's
(the designer's request, 2026-10-21), so the words and the feel match
what she sets in Figma prototypes.

Easing ("feel"), as in Figma's prototype animation settings:
  springs   gentle, quick, bouncy, slow, or spring with her own mass,
            stiffness and damping. A spring's length comes from the
            physics: a heavier mass is slower and swings further.
  curves    linear, ease-in, ease-out, ease-in-out, ease-in-back,
            ease-out-back, ease-in-out-back, or bezier with her own
            four numbers (CSS cubic-bezier).

Animations, as in Figma's transitions (dissolve, move in/out, slide
in/out, push) plus scale in and pop for brand pieces.

Everything here is plain numbers in, keyframes out, in Concat's units:
a key's `at` is a fraction of its clip, offsets are fractions of the
frame, scale 1 fits the frame. Curves go to Concat as they are (it keeps
overshooting beziers); springs are sampled into short linear steps.
The browser preview (web/static/motion.js) plays the same keyframes.
"""

from __future__ import annotations

import math

# Figma's bezier presets (the numbers Figma shows for each).
CURVES: dict[str, list[float]] = {
    "linear": [0.0, 0.0, 1.0, 1.0],
    "ease-in": [0.42, 0.0, 1.0, 1.0],
    "ease-out": [0.0, 0.0, 0.58, 1.0],
    "ease-in-out": [0.42, 0.0, 0.58, 1.0],
    "ease-in-back": [0.3, -0.05, 0.7, -0.5],
    "ease-out-back": [0.45, 1.45, 0.8, 1.0],
    "ease-in-out-back": [0.7, -0.4, 0.4, 1.4],
}

# Figma's spring presets (mass, stiffness, damping).
SPRINGS: dict[str, dict] = {
    "gentle": {"mass": 1.0, "stiffness": 100.0, "damping": 15.0},
    "quick": {"mass": 1.0, "stiffness": 300.0, "damping": 20.0},
    "bouncy": {"mass": 1.0, "stiffness": 600.0, "damping": 15.0},
    "slow": {"mass": 1.0, "stiffness": 80.0, "damping": 20.0},
}

FEELS = (*SPRINGS, "spring", *CURVES, "bezier")
DEFAULT_FEEL = {"type": "gentle"}  # Plamen: the motions could be gentle

ENTER_EFFECTS = ("dissolve", "slide-in", "move-in", "scale-in", "pop", "instant")
EXIT_EFFECTS = ("dissolve", "slide-out", "move-out", "scale-out")
DIRECTIONS = ("bottom", "top", "left", "right")  # where it comes from / goes to
TRANSITIONS = ("dissolve", "slide-in", "move-in", "push", "instant")
CAMERA_MOVES = ("none", "push-in", "pull-out", "pan-left", "pan-right", "pan-up", "pan-down")

SLIDE_OFFSET = 0.04      # Figma's slide: a gentle offset while it dissolves
SCALE_IN_FROM = 0.85
POP_FROM = 0.4           # Concat clamps scale at 0.05, so not from zero
SPRING_STEP_S = 1 / 30   # spring samples
SPRING_MAX_S = 4.0
SETTLE = 0.002           # a spring has arrived within 0.2%

LIMITS = {"mass": (0.1, 10.0), "stiffness": (1.0, 1000.0), "damping": (0.0, 100.0)}


class MotionError(ValueError):
    pass


# -- easing ----------------------------------------------------------------------------


def clean_easing(spec) -> dict:
    """A checked easing dict from what the UI or an assistant sent."""
    if spec is None:
        return dict(DEFAULT_FEEL)
    if isinstance(spec, str):
        spec = {"type": spec}
    kind = spec.get("type")
    if kind not in FEELS:
        raise MotionError(f"Unknown easing '{kind}'. Use one of: {', '.join(FEELS)}.")
    out = {"type": kind}
    if kind == "spring":
        base = SPRINGS["gentle"]
        for key, (lo, hi) in LIMITS.items():
            try:
                val = float(spec.get(key, base[key]))
            except (TypeError, ValueError) as exc:
                raise MotionError(f"Spring {key} must be a number.") from exc
            if not lo <= val <= hi or not math.isfinite(val):
                raise MotionError(f"Spring {key} must be between {lo:g} and {hi:g}.")
            out[key] = val
    elif kind == "bezier":
        pts = spec.get("points")
        try:
            pts = [float(p) for p in pts]
        except (TypeError, ValueError) as exc:
            raise MotionError("A bezier needs four numbers.") from exc
        if len(pts) != 4 or not (0 <= pts[0] <= 1 and 0 <= pts[2] <= 1):
            raise MotionError("A bezier needs four numbers, the 1st and 3rd between 0 and 1.")
        if not all(-2 <= p <= 3 for p in pts):
            raise MotionError("Bezier values must be between -2 and 3.")
        out["points"] = pts
    return out


def spring_params(easing: dict) -> dict | None:
    if easing["type"] in SPRINGS:
        return SPRINGS[easing["type"]]
    if easing["type"] == "spring":
        return {k: easing[k] for k in LIMITS}
    return None


def curve_points(easing: dict) -> list[float] | None:
    if easing["type"] in CURVES:
        return CURVES[easing["type"]]
    if easing["type"] == "bezier":
        return easing["points"]
    return None


def spring_value(p: dict, t: float) -> float:
    """Position 0 -> 1 of a spring released from rest, t seconds after."""
    m, k, c = p["mass"], p["stiffness"], p["damping"]
    w0 = math.sqrt(k / m)
    zeta = c / (2 * math.sqrt(k * m))
    if zeta < 1:
        wd = w0 * math.sqrt(1 - zeta * zeta)
        return 1 - math.exp(-zeta * w0 * t) * (math.cos(wd * t) + zeta * w0 / wd * math.sin(wd * t))
    if zeta == 1:
        return 1 - math.exp(-w0 * t) * (1 + w0 * t)
    r = math.sqrt(zeta * zeta - 1)
    r1, r2 = -w0 * (zeta - r), -w0 * (zeta + r)
    return 1 + (r2 * math.exp(r1 * t) - r1 * math.exp(r2 * t)) / (r1 - r2)


def spring_duration(p: dict) -> float:
    """How long the spring takes to settle, like the duration Figma shows."""
    last = 0.0
    t = 0.0
    while t <= SPRING_MAX_S:
        if abs(1 - spring_value(p, t)) > SETTLE:
            last = t
        t += 0.002
    return round(min(max(last, 0.1), SPRING_MAX_S), 3)


def bezier_value(pts: list[float], u: float) -> float:
    """CSS cubic-bezier: progress at time fraction u (0-1)."""
    x1, y1, x2, y2 = pts
    if u <= 0:
        return 0.0
    if u >= 1:
        return 1.0

    def bx(s):
        return 3 * x1 * s * (1 - s) ** 2 + 3 * x2 * s * s * (1 - s) + s ** 3

    def by(s):
        return 3 * y1 * s * (1 - s) ** 2 + 3 * y2 * s * s * (1 - s) + s ** 3

    lo, hi = 0.0, 1.0
    s = u
    for _ in range(60):  # bisection: x(s) is monotonic since x1, x2 are in [0, 1]
        x = bx(s)
        if abs(x - u) < 1e-7:
            break
        if x < u:
            lo = s
        else:
            hi = s
        s = (lo + hi) / 2
    return by(s)


def duration(easing: dict, wanted: float) -> float:
    """A spring's length is its own; a curve takes the length asked for."""
    p = spring_params(easing)
    return spring_duration(p) if p else max(float(wanted), 0.05)


def progress(easing: dict, t: float, length: float) -> float:
    if length <= 0:
        return 1.0
    p = spring_params(easing)
    if p:
        return spring_value(p, t) if t < length else 1.0
    return bezier_value(curve_points(easing), t / length)


# -- animations and their keyframes -------------------------------------------------


class Seg:
    """One animation of one property: from v0 to v1, `start` s into the
    clip, over `length` s, with an easing. Offsets add up; scale and
    opacity multiply, so a pan and a push on the same picture combine."""

    __slots__ = ("prop", "start", "length", "v0", "v1", "easing")

    def __init__(self, prop, start, length, v0, v1, easing):
        self.prop, self.start, self.length = prop, float(start), float(length)
        self.v0, self.v1, self.easing = float(v0), float(v1), easing

    @property
    def end(self) -> float:
        return self.start + self.length

    def at(self, t: float) -> float:
        if t <= self.start:
            return self.v0
        if t >= self.end:
            return self.v1
        return self.v0 + (self.v1 - self.v0) * progress(self.easing, t - self.start, self.length)


ADDITIVE = {"offsetX", "offsetY"}


def value_at(prop: str, base: float, segs: list[Seg], t: float) -> float:
    own = [s for s in segs if s.prop == prop]
    if prop in ADDITIVE:
        v = base + sum(s.at(t) for s in own)
    else:
        v = base
        for s in own:
            v *= s.at(t)
    if prop == "opacity":
        v = min(max(v, 0.0), 1.0)
    elif prop == "scale":
        v = min(max(v, 0.05), 8.0)  # Concat's own clamp
    return v


def keys_for(prop: str, base: float, segs: list[Seg], clip_len: float) -> list[dict]:
    """Concat keys for one property. A lone curve stays two keys with the
    curve on the second (editable in Concat); springs and overlapping
    moves are sampled into short linear steps."""
    own = sorted((s for s in segs if s.prop == prop), key=lambda s: s.start)
    if not own:
        return []
    clip_len = max(clip_len, 1e-3)

    def key(t, ease=None):
        k = {"property": prop, "at": round(min(max(t / clip_len, 0.0), 1.0), 5),
             "value": round(value_at(prop, base, segs, t), 5)}
        if ease is not None:
            k["ease"] = list(ease)
        return k

    # windows of overlapping segments
    windows: list[list[Seg]] = []
    for s in own:
        if windows and s.start < max(x.end for x in windows[-1]) - 1e-6:
            windows[-1].append(s)
        else:
            windows.append([s])
    keys: list[dict] = []
    for win in windows:
        start, end = win[0].start, max(x.end for x in win)
        pts = curve_points(win[0].easing) if len(win) == 1 else None
        if pts and prop == "opacity" and (min(pts[1], pts[3]) < 0 or max(pts[1], pts[3]) > 1):
            pts = None  # an overshooting curve can't overshoot opacity: sample, clamped
        keys.append(key(start))
        if pts:
            keys.append(key(end, pts))
            continue
        n = max(int(math.ceil((end - start) / SPRING_STEP_S)), 1)
        for i in range(1, n + 1):
            keys.append(key(min(start + i * SPRING_STEP_S, end)))
    # drop exact repeats (same place, same value) a window boundary leaves
    out: list[dict] = []
    for k in keys:
        if out and out[-1]["at"] == k["at"]:
            out[-1] = k
        else:
            out.append(k)
    return out


def all_keys(base: dict, segs: list[Seg], clip_len: float) -> list[dict]:
    """Keys for every animated property; `base` = the clip's resting
    {scale, offsetX, offsetY, opacity}."""
    out: list[dict] = []
    for prop in ("opacity", "scale", "offsetX", "offsetY"):
        out += keys_for(prop, base.get(prop, 1.0 if prop in ("scale", "opacity") else 0.0),
                        segs, clip_len)
    return out


def _edge_delta(direction: str, size_frac: tuple[float, float],
                offset: tuple[float, float]) -> tuple[float, float]:
    """How far to move a layer resting at `offset` so it sits just outside
    the frame on `direction`."""
    w, h = size_frac
    ox, oy = offset
    return {"bottom": (0.0, 0.5 + h / 2 + 0.01 - oy), "top": (0.0, -0.5 - h / 2 - 0.01 - oy),
            "left": (-0.5 - w / 2 - 0.01 - ox, 0.0),
            "right": (0.5 + w / 2 + 0.01 - ox, 0.0)}[direction]


def _slide_delta(direction: str, amount: float = SLIDE_OFFSET) -> tuple[float, float]:
    return {"bottom": (0.0, amount), "top": (0.0, -amount), "left": (-amount, 0.0),
            "right": (amount, 0.0)}[direction]


def _moves(dx, dy, start, length, easing, coming: bool) -> list[Seg]:
    out = []
    for prop, d in (("offsetX", dx), ("offsetY", dy)):
        if d:
            out.append(Seg(prop, start, length, d if coming else 0.0, 0.0 if coming else d,
                           easing))
    return out


def enter(effect: str, direction: str, easing: dict, start: float, length: float,
          size_frac: tuple[float, float], offset: tuple[float, float]) -> list[Seg]:
    """A piece coming in, `start` s into its clip."""
    if effect == "instant":
        return [Seg("opacity", start, 0.04, 0.0, 1.0, {"type": "linear"})]  # one frame
    segs = []
    if effect == "pop":
        segs.append(Seg("opacity", start, min(length, 0.25), 0.0, 1.0, {"type": "ease-out"}))
    elif effect != "move-in":  # move in arrives from outside the frame, fully there
        segs.append(Seg("opacity", start, length, 0.0, 1.0, easing))
    if effect == "slide-in":
        segs += _moves(*_slide_delta(direction), start, length, easing, coming=True)
    elif effect == "move-in":
        segs += _moves(*_edge_delta(direction, size_frac, offset), start, length, easing,
                       coming=True)
    elif effect in ("scale-in", "pop"):
        segs.append(Seg("scale", start, length, SCALE_IN_FROM if effect == "scale-in"
                        else POP_FROM, 1.0, easing))
    return segs


def leave(effect: str, direction: str, easing: dict, start: float, length: float,
          size_frac: tuple[float, float], offset: tuple[float, float]) -> list[Seg]:
    segs = []
    if effect != "move-out":
        segs.append(Seg("opacity", start, length, 1.0, 0.0, easing))
    if effect == "slide-out":
        segs += _moves(*_slide_delta(direction), start, length, easing, coming=False)
    elif effect == "move-out":
        segs += _moves(*_edge_delta(direction, size_frac, offset), start, length, easing,
                       coming=False)
    elif effect == "scale-out":
        segs.append(Seg("scale", start, length, 1.0, SCALE_IN_FROM, easing))
    return segs


def camera(move: str, amount_pct: float, start: float, length: float,
           easing: dict | None = None) -> tuple[float, list[Seg]]:
    """A slow move on her static: push in / pull out (zoom), or pan
    (drift) left, right, up or down. Returns the base scale and the
    moves. A pan zooms in by `amount` first so no edge ever shows."""
    a = min(max(float(amount_pct), 0.0), 30.0) / 100
    easing = easing or {"type": "ease-in-out"}
    if move == "none" or a == 0:
        return 1.0, []
    if move == "push-in":
        return 1.0, [Seg("scale", start, length, 1.0, 1.0 + a, easing)]
    if move == "pull-out":
        return 1.0 + a, [Seg("scale", start, length, 1.0, 1.0 / (1.0 + a), easing)]
    half = a / 2
    prop, v0, v1 = {"pan-left": ("offsetX", half, -half), "pan-right": ("offsetX", -half, half),
                    "pan-up": ("offsetY", half, -half),
                    "pan-down": ("offsetY", -half, half)}[move]
    return 1.0 + a, [Seg(prop, start, length, v0, v1, easing)]


def transition(kind: str, direction: str, easing: dict, at: float, length: float
               ) -> tuple[list[Seg], list[Seg]]:
    """Picture A to picture B, as Figma's transitions. B's clip starts at
    `at` (timeline seconds); A's at 0. Returns (A's moves, B's moves).
    `direction` is where B comes from. Push moves A out the other way."""
    if kind == "instant":
        return [], [Seg("opacity", 0.0, 0.04, 0.0, 1.0, {"type": "linear"})]
    if kind == "dissolve":
        return [], [Seg("opacity", 0.0, length, 0.0, 1.0, easing)]
    dx, dy = _slide_delta(direction, 1.0)
    a: list[Seg] = []
    b: list[Seg] = []
    if kind == "slide-in":
        dx, dy = dx * SLIDE_OFFSET * 3, dy * SLIDE_OFFSET * 3
        b.append(Seg("opacity", 0.0, length, 0.0, 1.0, easing))
    b += _moves(dx, dy, 0.0, length, easing, coming=True)
    if kind == "push":
        a += _moves(-dx, -dy, at, length, easing, coming=False)
    return a, b
