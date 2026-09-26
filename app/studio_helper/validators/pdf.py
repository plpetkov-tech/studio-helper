"""PDF validator (SPEC.md §6.7).

Checks structure with pypdf (boxes, PDF/X markers, fonts, color
spaces) and renders with pypdfium2 for the two checks that need pixel
data: per-image effective ppi, and bleed coverage (does the artwork
actually reach the bleed edge on every side).
"""

from __future__ import annotations

from pathlib import Path

import pypdf
import pypdfium2 as pdfium
from pypdf.generic import ContentStream

from . import match
from .model import Check

PT_PER_MM = 72 / 25.4
BOX_TOLERANCE_MM = 0.2
BLEED_ALPHA_FAIL_FRACTION = 0.001  # 0.1% of a strip's pixels
ALPHA_THRESHOLD = 250
RGB_OPERATORS = {b"rg", b"RG"}


def _mm(pt: float) -> float:
    return pt / PT_PER_MM


def _pt(mm: float) -> float:
    return mm * PT_PER_MM


def validate(path: Path, fmt: dict, deliverable: dict) -> list[Check]:
    reader = pypdf.PdfReader(str(path))
    checks: list[Check] = []

    page_count_check, ok = _check_page_count(reader)
    checks.append(page_count_check)
    if not ok:
        return checks

    page = reader.pages[0]
    # A 1:10 artboard exports a 1:10 PDF: size and bleed both scaled.
    scale = fmt.get("scale", 1) or 1
    w_mm, h_mm = match.deliverable_size(fmt, deliverable)
    w_mm, h_mm = w_mm * scale, h_mm * scale
    bleed_mm = (fmt.get("bleed_mm", 0) or 0) * scale

    trim_box = _raw_box(page, "/TrimBox")
    checks.append(_check_trimbox(trim_box, w_mm, h_mm))

    bleed_box = _raw_box(page, "/BleedBox")
    checks.append(_check_bleedbox(bleed_box, trim_box, w_mm, h_mm, bleed_mm))

    checks.append(_check_pdfx(reader))
    checks.extend(_check_fonts(page))
    checks.append(_check_rgb(page))
    checks.extend(_check_image_ppi(path, fmt.get("min_image_ppi", {})))

    if bleed_box is not None and bleed_mm > 0:
        checks.append(_check_bleed_coverage(path, page, trim_box, bleed_box))

    return checks


# -- structural checks -------------------------------------------------


def _check_page_count(reader: pypdf.PdfReader) -> tuple[Check, bool]:
    count = len(reader.pages)
    if count != 1:
        return (
            Check(
                "page-count",
                "fail",
                f"This PDF has {count} pages; it should have exactly 1.",
                "Export one artboard per PDF (use artboardRange when exporting from Illustrator).",
            ),
            False,
        )
    return Check("page-count", "ok", "One page, as expected."), True


def _raw_box(page, key: str):
    """The box only if the key is actually present on this page dict
    -- unlike page.trimbox/.bleedbox, which silently fall back to the
    MediaBox per PDF inheritance rules, hiding a missing box from us."""
    if key not in page:
        return None
    return pypdf.generic.RectangleObject(page[key])


def _check_trimbox(trim_box, w_mm: float, h_mm: float) -> Check:
    if trim_box is None:
        return Check(
            "trimbox",
            "fail",
            "This PDF has no TrimBox.",
            "Re-export with the trim size set to the artboard bounds (not including bleed).",
        )
    actual_w = _mm(float(trim_box.width))
    actual_h = _mm(float(trim_box.height))
    if abs(actual_w - w_mm) > BOX_TOLERANCE_MM or abs(actual_h - h_mm) > BOX_TOLERANCE_MM:
        return Check(
            "trimbox",
            "fail",
            f"TrimBox is {actual_w:.1f}×{actual_h:.1f}mm; expected {w_mm}×{h_mm}mm.",
            "Check the artboard size matches this format in the registry.",
        )
    return Check("trimbox", "ok", "TrimBox matches the expected size.")


def _check_bleedbox(bleed_box, trim_box, w_mm: float, h_mm: float, bleed_mm: float) -> Check:
    if bleed_mm <= 0:
        return Check("bleedbox", "ok", "This format has no bleed requirement.")
    if bleed_box is None:
        return Check(
            "bleedbox",
            "fail",
            "This PDF has no BleedBox.",
            f"Re-export with a {bleed_mm}mm bleed set on the document.",
        )
    expected_w = w_mm + 2 * bleed_mm
    expected_h = h_mm + 2 * bleed_mm
    actual_w = _mm(float(bleed_box.width))
    actual_h = _mm(float(bleed_box.height))
    w_off = abs(actual_w - expected_w) > BOX_TOLERANCE_MM
    h_off = abs(actual_h - expected_h) > BOX_TOLERANCE_MM
    if w_off or h_off:
        return Check(
            "bleedbox",
            "fail",
            f"BleedBox is {actual_w:.1f}×{actual_h:.1f}mm; expected "
            f"{expected_w:.1f}×{expected_h:.1f}mm ({bleed_mm}mm bleed).",
            "Check the document bleed matches this format in the registry.",
        )
    return Check("bleedbox", "ok", "BleedBox matches TrimBox plus the expected bleed.")


def _check_pdfx(reader: pypdf.PdfReader) -> Check:
    has_marker = False
    try:
        info = reader.trailer.get("/Info")
        if info is not None and "/GTS_PDFXVersion" in info.get_object():
            has_marker = True
    except Exception:
        pass
    if not has_marker:
        try:
            root = reader.trailer["/Root"]
            metadata = root.get("/Metadata")
            if metadata is not None:
                data = metadata.get_object().get_data()
                if b"GTS_PDFXVersion" in data or b"pdfxid" in data.lower():
                    has_marker = True
        except Exception:
            pass

    has_output_intents = False
    try:
        root = reader.trailer["/Root"]
        intents = root.get("/OutputIntents")
        has_output_intents = bool(intents and len(intents) > 0)
    except Exception:
        pass

    if has_marker and has_output_intents:
        return Check("pdfx", "ok", "Exported as PDF/X-1a with an output intent.")

    missing = []
    if not has_marker:
        missing.append("a PDF/X version marker")
    if not has_output_intents:
        missing.append("an OutputIntent")
    return Check(
        "pdfx",
        "fail",
        f"Not a valid PDF/X-1a export: missing {' and '.join(missing)}.",
        "Re-export using the studio's PDF/X-1a preset.",
    )


# -- fonts -------------------------------------------------------------


def _iter_fonts(resources, seen: set):
    if resources is None:
        return
    fonts = resources.get("/Font")
    if fonts:
        for font_ref in fonts.values():
            yield font_ref.get_object()
    xobjects = resources.get("/XObject")
    if xobjects:
        for xobj_ref in xobjects.values():
            xobj = xobj_ref.get_object()
            if xobj.get("/Subtype") != "/Form":
                continue
            key = id(xobj)
            if key in seen:
                continue
            seen.add(key)
            yield from _iter_fonts(xobj.get("/Resources"), seen)


def _font_is_embedded(font) -> bool:
    if font.get("/Subtype") == "/Type3":
        return True  # Type3 fonts are drawn, not embedded (SPEC.md §6.7)
    descriptor = font.get("/FontDescriptor")
    if descriptor is not None:
        d = descriptor.get_object()
        return any(k in d for k in ("/FontFile", "/FontFile2", "/FontFile3"))
    descendants = font.get("/DescendantFonts")
    if descendants:
        for d_ref in descendants:
            d = d_ref.get_object()
            desc = d.get("/FontDescriptor")
            if desc is not None and any(
                k in desc.get_object() for k in ("/FontFile", "/FontFile2", "/FontFile3")
            ):
                return True
    return False


def _check_fonts(page) -> list[Check]:
    missing = []
    seen: set = set()
    for font in _iter_fonts(page.get("/Resources"), seen):
        if not _font_is_embedded(font):
            base_font = str(font.get("/BaseFont", "unknown font"))
            if base_font not in missing:
                missing.append(base_font)

    if missing:
        return [
            Check(
                "fonts",
                "fail",
                f"Font(s) not embedded: {', '.join(missing)}.",
                "In Illustrator, embed all fonts before exporting (or outline the text).",
            )
        ]
    return [Check("fonts", "ok", "All fonts are embedded.")]


# -- color spaces -------------------------------------------------------


def _is_rgb_color_space(cs) -> bool:
    if cs == "/DeviceRGB":
        return True
    if isinstance(cs, list) and len(cs) >= 1:
        family = cs[0]
        if family == "/ICCBased":
            stream = cs[1].get_object()
            if stream.get("/N") == 3:
                return True
        if family == "/CalRGB":
            return True
    return False


def _resources_have_rgb(resources, seen: set) -> bool:
    if resources is None:
        return False
    color_spaces = resources.get("/ColorSpace")
    if color_spaces:
        for cs_ref in color_spaces.values():
            cs_obj = cs_ref.get_object() if hasattr(cs_ref, "get_object") else cs_ref
            if _is_rgb_color_space(cs_obj):
                return True
    xobjects = resources.get("/XObject")
    if xobjects:
        for xobj_ref in xobjects.values():
            xobj = xobj_ref.get_object()
            key = id(xobj)
            if key in seen:
                continue
            seen.add(key)
            if xobj.get("/Subtype") == "/Image":
                cs = xobj.get("/ColorSpace")
                if cs is not None:
                    cs_obj = cs.get_object() if hasattr(cs, "get_object") else cs
                    if _is_rgb_color_space(cs_obj):
                        return True
            elif xobj.get("/Subtype") == "/Form":
                if _resources_have_rgb(xobj.get("/Resources"), seen):
                    return True
    return False


def _content_uses_rgb_operator(page) -> bool:
    contents = page.get_contents()
    if contents is None:
        return False
    try:
        stream = ContentStream(contents, page.pdf)
    except Exception:
        return False
    return any(operator in RGB_OPERATORS for _operands, operator in stream.operations)


def _check_rgb(page) -> Check:
    if _content_uses_rgb_operator(page) or _resources_have_rgb(page.get("/Resources"), set()):
        return Check(
            "color-space",
            "fail",
            "This PDF uses RGB color (DeviceRGB or an RGB ICC profile).",
            "Convert all content and placed images to CMYK before exporting.",
        )
    return Check("color-space", "ok", "No RGB color space found.")


# -- image ppi (pypdfium2) -----------------------------------------------


def _check_image_ppi(path: Path, min_image_ppi: dict) -> list[Check]:
    warn_ppi = min_image_ppi.get("warn")
    fail_ppi = min_image_ppi.get("fail")
    if warn_ppi is None and fail_ppi is None:
        return []

    checks = []
    pdf = pdfium.PdfDocument(str(path))
    try:
        page = pdf[0]
        for obj in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE]):
            try:
                px_w, px_h = obj.get_px_size()
                left, bottom, right, top = obj.get_bounds()
            except Exception:
                continue
            placed_w_in = (right - left) / 72
            placed_h_in = (top - bottom) / 72
            if placed_w_in <= 0 or placed_h_in <= 0:
                continue
            effective_ppi = min(px_w / placed_w_in, px_h / placed_h_in)
            position = f"near ({_mm(left):.0f}mm, {_mm(bottom):.0f}mm)"

            if fail_ppi is not None and effective_ppi < fail_ppi:
                checks.append(
                    Check(
                        "image-ppi",
                        "fail",
                        f"An image is only {effective_ppi:.0f} ppi {position}; "
                        f"needs at least {fail_ppi}.",
                        "Replace it with a higher-resolution image, or scale it down.",
                    )
                )
            elif warn_ppi is not None and effective_ppi < warn_ppi:
                checks.append(
                    Check(
                        "image-ppi",
                        "warn",
                        f"An image is only {effective_ppi:.0f} ppi {position}; "
                        f"{warn_ppi} is recommended.",
                        "Consider a higher-resolution image for the best print quality.",
                    )
                )
    finally:
        pdf.close()

    if not checks:
        checks.append(Check("image-ppi", "ok", "All images meet the minimum resolution."))
    return checks


# -- bleed coverage (render + alpha, pypdfium2) -------------------------


def _check_bleed_coverage(path: Path, page, trim_box, bleed_box) -> Check:
    pdf = pdfium.PdfDocument(str(path))
    try:
        pdfium_page = pdf[0]
        media_left, _media_bottom, _media_right, media_top = pdfium_page.get_mediabox()
        bitmap = pdfium_page.render(scale=1.0, fill_color=(0, 0, 0, 0), draw_annots=False)
        image = bitmap.to_pil()
    finally:
        pdf.close()

    def to_px(pt_x: float, pt_y: float) -> tuple[int, int]:
        return round(pt_x - media_left), round(media_top - pt_y)

    trim_l, trim_b, trim_r, trim_t = float(trim_box.left), float(trim_box.bottom), float(
        trim_box.right
    ), float(trim_box.top)
    bleed_l, bleed_b, bleed_r, bleed_t = float(bleed_box.left), float(bleed_box.bottom), float(
        bleed_box.right
    ), float(bleed_box.top)

    bx0, by0 = to_px(bleed_l, bleed_t)  # top-left of bleed box, in pixels
    bx1, by1 = to_px(bleed_r, bleed_b)  # bottom-right
    tx0, ty0 = to_px(trim_l, trim_t)
    tx1, ty1 = to_px(trim_r, trim_b)

    def below_threshold_count(box: tuple[int, int, int, int]) -> tuple[int, int]:
        left, top, right, bottom = box
        if right <= left or bottom <= top:
            return 0, 0
        region = image.crop((left, top, right, bottom))
        alpha_hist = region.getchannel("A").histogram()
        return sum(alpha_hist[:ALPHA_THRESHOLD]), region.width * region.height

    # Overall check (SPEC.md §6.7): the whole ring between TrimBox and
    # BleedBox, as one fraction. Computed as bleed-crop minus the
    # trim-crop it contains, rather than an L-shaped mask.
    bleed_below, bleed_total = below_threshold_count((bx0, by0, bx1, by1))
    trim_below, trim_total = below_threshold_count((tx0, ty0, tx1, ty1))
    ring_below = bleed_below - trim_below
    ring_total = bleed_total - trim_total

    if ring_total <= 0 or (ring_below / ring_total) <= BLEED_ALPHA_FAIL_FRACTION:
        return Check("bleed-coverage", "ok", "The background covers the bleed on every edge.")

    # Diagnostic breakdown: which edge(s) to name. Each strip excludes
    # the corners (shared with its neighbors) so one bad edge can't
    # make an adjacent good edge look bad too.
    edge_strips = {
        "top": (tx0, by0, tx1, ty0),
        "bottom": (tx0, ty1, tx1, by1),
        "left": (bx0, ty0, tx0, ty1),
        "right": (tx1, ty0, bx1, ty1),
    }
    failing_edges = []
    for edge, box in edge_strips.items():
        below, total = below_threshold_count(box)
        if total and (below / total) > BLEED_ALPHA_FAIL_FRACTION:
            failing_edges.append(edge)

    edges = ", ".join(failing_edges) if failing_edges else "bleed"
    return Check(
        "bleed-coverage",
        "fail",
        f"The background doesn't reach the bleed on the {edges} edge(s).",
        f"Extend the background past the artboard edge on the {edges} side(s).",
    )
