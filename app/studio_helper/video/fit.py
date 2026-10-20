"""Fitting one master video onto a screen around her juice box (ROADMAP R6).

The rule: zoom in as far as possible while the whole juice box (what must
stay visible, which she draws) stays on screen. Fill (blur, black or a
colour behind the picture) appears only where the box can't fit the
screen's shape. Platform UI bands on stories (ui_safe_px) count as
covered: the juice box is kept between them.

Coordinates: source pixels, y down. Concat's units: scale 1 fits the
whole picture in the frame; offsets are fractions of the frame from the
centre, positive right/down.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass(frozen=True)
class Fit:
    scale: float        # screen pixels per source pixel
    left: float         # where the source's top-left lands on the screen
    top: float
    concat_scale: float  # Concat's scale (1 = whole picture fits the frame)
    offset_x: float     # Concat's offsets: fractions of the frame from the centre
    offset_y: float
    fill_fraction: float  # share of the screen the picture doesn't cover
    upscale: float      # > 1 when the master is enlarged


def juice_box(fractions: list[float] | tuple[float, ...] | None, sw: float, sh: float) -> Box:
    """Her drawn box [x, y, w, h] as fractions of the master frame. With
    none drawn, the centre: a plain cover crop, nothing has to stay."""
    if not fractions:
        return Box(sw / 2 - 0.5, sh / 2 - 0.5, 1, 1)
    x, y, w, h = fractions
    return Box(x * sw, y * sh, max(w * sw, 1), max(h * sh, 1))


def max_scale(sw, sh, dw, dh, juice: Box, top: float = 0, bottom: float = 0) -> float:
    cover = max(dw / sw, dh / sh)
    safe_h = max(dh - top - bottom, 1)
    return min(cover, dw / juice.w, safe_h / juice.h)


def place(sw, sh, dw, dh, juice: Box, s: float, top: float = 0, bottom: float = 0) -> Fit:
    """Puts the juice box's centre in the middle of the screen's safe area
    at scale s, then slides the picture back so it covers every edge it can."""
    safe_cy = top + (dh - top - bottom) / 2

    def axis(src_len, dst_len, centre_src, centre_dst):
        size = src_len * s
        if size <= dst_len:
            return (dst_len - size) / 2  # smaller than the screen: centre it, fill shows
        start = centre_dst - centre_src * s
        return min(0.0, max(dst_len - size, start))

    left = axis(sw, dw, juice.cx, dw / 2)
    top_px = axis(sh, dh, juice.cy, safe_cy)
    fit_scale = min(dw / sw, dh / sh)
    covered_w = min(dw, left + sw * s) - max(0.0, left)
    covered_h = min(dh, top_px + sh * s) - max(0.0, top_px)
    return Fit(
        scale=s,
        left=left,
        top=top_px,
        concat_scale=s / fit_scale,
        offset_x=(left + sw * s / 2 - dw / 2) / dw,
        offset_y=(top_px + sh * s / 2 - dh / 2) / dh,
        fill_fraction=round(1 - max(covered_w, 0) * max(covered_h, 0) / (dw * dh), 6),
        upscale=s,
    )


def fit(sw, sh, dw, dh, juice: Box | None = None, top: float = 0, bottom: float = 0) -> Fit:
    juice = juice or juice_box(None, sw, sh)
    return place(sw, sh, dw, dh, juice, max_scale(sw, sh, dw, dh, juice, top, bottom), top, bottom)


def fit_keyed(sw, sh, dw, dh, keys: list[tuple[float, Box]], top: float = 0,
              bottom: float = 0) -> list[tuple[float, Fit]]:
    """A juice box drawn on several moments of the video: one constant
    zoom (the smallest any moment needs, so the picture never pumps) and
    a moving position, keyed at each moment (seconds)."""
    if not keys:
        return [(0.0, fit(sw, sh, dw, dh, None, top, bottom))]
    s = min(max_scale(sw, sh, dw, dh, box, top, bottom) for _t, box in keys)
    return [(t, place(sw, sh, dw, dh, box, s, top, bottom)) for t, box in sorted(keys)]


def panel_widths(dw: float, n: int, frame_px: float) -> list[float]:
    """Repeat mode for wrap-around screens (the Paradise column): n equal
    columns with frame lines between them."""
    usable = dw - frame_px * (n - 1)
    return [usable / n] * n


@dataclass(frozen=True)
class PanelPlacement:
    """One column of a Repeat layout, in Concat terms: the master cropped
    to what the column shows (Concat then treats the crop as the
    picture), scaled and centred in its column."""
    crop: dict
    concat_scale: float
    offset_x: float
    offset_y: float
    fill_fraction: float


def repeat_panels(sw, sh, dw, dh, n: int, frame_px: float, juice: Box | None = None
                  ) -> list[PanelPlacement]:
    """Repeat mode for wrap-around screens (the Paradise column: one
    picture only shows from one side): the same fitted picture in n
    columns with frame lines between them, delivered as one file."""
    juice = juice or juice_box(None, sw, sh)
    out = []
    pw = panel_widths(dw, n, frame_px)[0]
    for i in range(n):
        f = fit(sw, sh, pw, dh, juice)
        s = f.scale
        x0, x1 = max(0.0, -f.left / s), min(sw, (pw - f.left) / s)
        y0, y1 = max(0.0, -f.top / s), min(sh, (dh - f.top) / s)
        cw, ch = x1 - x0, y1 - y0
        panel_x = i * (pw + frame_px)
        cx = panel_x + f.left + (x0 + cw / 2) * s
        cy = f.top + (y0 + ch / 2) * s
        out.append(PanelPlacement(
            crop={"left": x0 / sw, "right": 1 - x1 / sw, "top": y0 / sh, "bottom": 1 - y1 / sh},
            concat_scale=s / min(dw / cw, dh / ch),
            offset_x=(cx - dw / 2) / dw,
            offset_y=(cy - dh / 2) / dh,
            fill_fraction=f.fill_fraction,
        ))
    return out
