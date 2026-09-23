"""PNG/JPG validator (SPEC.md §6.7)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageCms

from . import match
from .model import Check


def validate(path: Path, fmt: dict, deliverable: dict) -> list[Check]:
    checks: list[Check] = []
    with Image.open(path) as img:
        checks.append(_check_dimensions(img, fmt, deliverable))
        checks.append(_check_mode(img, fmt))
        checks.append(_check_icc_profile(img))
    checks.append(_check_max_kb(path, fmt))
    return checks


def _check_dimensions(img: Image.Image, fmt: dict, deliverable: dict) -> Check:
    w, h = match.deliverable_size(fmt, deliverable)
    actual_w, actual_h = img.size
    if (actual_w, actual_h) != (round(w), round(h)):
        return Check(
            "dimensions",
            "fail",
            f"This image is {actual_w}×{actual_h}px; expected {round(w)}×{round(h)}px.",
            "Re-export at the exact pixel size set for this format.",
        )
    return Check("dimensions", "ok", "Pixel dimensions match exactly.")


def _check_mode(img: Image.Image, fmt: dict) -> Check:
    allow_alpha = fmt.get("allow_alpha", False)
    allowed = {"RGB", "RGBA"} if allow_alpha else {"RGB"}
    if img.mode not in allowed:
        if img.mode == "RGBA" and not allow_alpha:
            return Check(
                "color-mode",
                "fail",
                "This image has transparency, which isn't allowed for this format.",
                "Flatten to a solid background before exporting.",
            )
        return Check(
            "color-mode",
            "fail",
            f"This image is {img.mode}; it should be RGB.",
            "Convert to RGB before exporting.",
        )
    return Check("color-mode", "ok", f"{img.mode}, as expected.")


def _check_icc_profile(img: Image.Image) -> Check:
    icc_bytes = img.info.get("icc_profile")
    if not icc_bytes:
        return Check("color-profile", "ok", "No embedded color profile (assumed sRGB).")
    try:
        import io

        profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_bytes))
        description = ImageCms.getProfileDescription(profile) or ""
    except Exception:
        return Check(
            "color-profile",
            "warn",
            "This image has a color profile that couldn't be read.",
            "Re-export with a standard sRGB profile.",
        )
    if "srgb" in description.lower():
        return Check("color-profile", "ok", "sRGB profile embedded.")
    return Check(
        "color-profile",
        "warn",
        f"This image uses the '{description.strip()}' color profile instead of sRGB.",
        "Convert to sRGB before exporting -- other profiles can look wrong on screens.",
    )


def _check_max_kb(path: Path, fmt: dict) -> Check:
    max_kb = fmt.get("max_kb")
    if not max_kb:
        return Check("file-size", "ok", "No file size limit configured for this format.")
    size_kb = path.stat().st_size / 1024
    if size_kb > max_kb:
        return Check(
            "file-size",
            "warn",
            f"This file is {size_kb:.0f}KB; the limit for this format is {max_kb}KB.",
            "Re-export at a lower quality or smaller size.",
        )
    return Check("file-size", "ok", f"{size_kb:.0f}KB, within the {max_kb}KB limit.")
