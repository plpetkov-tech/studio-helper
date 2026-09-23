"""Generates the validator test fixtures (SPEC.md §9). Dev-only:
needs reportlab, which is not part of the shipped runtime.

Fixtures are built, not committed -- see tests/validators/conftest.py,
which calls build_all() once per test session into a tmp directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import pypdf
import reportlab
from PIL import Image
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

PT_PER_MM = 72 / 25.4
VERA_TTF = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"

# A shared print-format shape used by most PDF fixtures.
A5 = {"w_mm": 148, "h_mm": 210, "bleed_mm": 3}


def build_all(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    _make_good_a5_pdf(output_dir / "good_a5.pdf")
    _make_bleed_short_pdf(output_dir / "bleed_short_left_bottom.pdf")
    _make_rgb_image_pdf(output_dir / "rgb_image.pdf")
    _make_lowres_pdf(output_dir / "lowres_150ppi.pdf")
    _make_font_not_embedded_pdf(output_dir / "font_not_embedded.pdf")
    _make_no_bleedbox_pdf(output_dir / "no_bleedbox.pdf")
    _make_no_pdfx_pdf(output_dir / "no_pdfx.pdf")
    _make_multipage_pdf(output_dir / "two_pages.pdf")

    _make_good_tiff(output_dir / "good_a5.tiff")
    _make_wrong_mode_tiff(output_dir / "wrong_mode.tiff")

    _make_good_png(output_dir / "good_ig_post.png")
    _make_wrong_dims_png(output_dir / "wrong_dims.png")
    _make_unwanted_alpha_png(output_dir / "unwanted_alpha.png")

    return output_dir


# -- shared helpers ------------------------------------------------------


def _page_size_pt(spec: dict = A5) -> tuple[float, float, float, float, float]:
    w = spec["w_mm"] * PT_PER_MM
    h = spec["h_mm"] * PT_PER_MM
    bleed = spec["bleed_mm"] * PT_PER_MM
    return w, h, bleed, w + 2 * bleed, h + 2 * bleed


def _finalize(path: Path, *, keep_helvetica: bool, pdfx: bool, output_intent: bool) -> None:
    """Post-processes a reportlab-generated PDF: reportlab always
    declares an unused default Helvetica font resource (with no
    FontDescriptor) whether or not it's actually drawn with, which
    would otherwise make every fixture fail the embedded-fonts check
    for no reason -- stripped here unless the fixture wants it kept
    (font_not_embedded.pdf). Also adds the PDF/X-1a markers reportlab
    has no native support for.
    """
    reader = pypdf.PdfReader(str(path))
    writer = pypdf.PdfWriter()
    writer.append(reader)

    if not keep_helvetica:
        page = writer.pages[0]
        resources = page.get("/Resources")
        fonts = resources.get("/Font") if resources else None
        if fonts:
            fonts_obj = fonts.get_object()
            unused = [
                name
                for name, ref in fonts_obj.items()
                if ref.get_object().get("/BaseFont") == "/Helvetica"
                and ref.get_object().get("/FontDescriptor") is None
            ]
            for name in unused:
                del fonts_obj[name]

    if pdfx:
        writer.add_metadata({"/GTS_PDFXVersion": "PDF/X-1a:2001"})

    if output_intent:
        oi = DictionaryObject()
        oi.update(
            {
                NameObject("/Type"): NameObject("/OutputIntent"),
                NameObject("/S"): NameObject("/GTS_PDFX"),
                NameObject("/OutputConditionIdentifier"): TextStringObject("Fixture CMYK"),
            }
        )
        # pypdf has no public "add an ad-hoc object" API as of 6.19;
        # _add_object is the documented workaround, fine in this
        # dev-only fixture generator.
        oi_ref = writer._add_object(oi)  # noqa: SLF001
        writer.root_object[NameObject("/OutputIntents")] = ArrayObject([oi_ref])

    with open(path, "wb") as fh:
        writer.write(fh)


def _use_vera(c: canvas.Canvas, size: int = 14) -> None:
    if "Vera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Vera", str(VERA_TTF)))
    c.setFont("Vera", size)


# -- PDF fixtures --------------------------------------------------------


def _make_good_a5_pdf(dest: Path) -> None:
    w, h, bleed, page_w, page_h = _page_size_pt()
    c = canvas.Canvas(str(dest), pagesize=(page_w, page_h))
    c.setTrimBox((bleed, bleed, bleed + w, bleed + h))
    c.setBleedBox((0, 0, page_w, page_h))
    c.setFillColorCMYK(0, 0, 0, 1)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)
    c.setFillColorCMYK(0, 0, 0, 0)
    _use_vera(c)
    c.drawString(bleed + 10, bleed + 10, "Autumn Sale")
    c.showPage()
    c.save()
    _finalize(dest, keep_helvetica=False, pdfx=True, output_intent=True)


def _make_bleed_short_pdf(dest: Path) -> None:
    w, h, bleed, page_w, page_h = _page_size_pt()
    c = canvas.Canvas(str(dest), pagesize=(page_w, page_h))
    c.setTrimBox((bleed, bleed, bleed + w, bleed + h))
    c.setBleedBox((0, 0, page_w, page_h))
    c.setFillColorCMYK(0, 0, 0, 1)
    # Reaches the bleed edge on the right/top, stops at the trim line
    # (not into the bleed) on the left/bottom.
    c.rect(bleed, bleed, page_w - bleed, page_h - bleed, fill=1, stroke=0)
    c.showPage()
    c.save()
    _finalize(dest, keep_helvetica=False, pdfx=True, output_intent=True)


def _make_rgb_image_pdf(dest: Path) -> None:
    w, h, bleed, page_w, page_h = _page_size_pt()
    c = canvas.Canvas(str(dest), pagesize=(page_w, page_h))
    c.setTrimBox((bleed, bleed, bleed + w, bleed + h))
    c.setBleedBox((0, 0, page_w, page_h))
    c.setFillColorCMYK(0, 0, 0, 1)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)
    c.setFillColorRGB(1, 0, 0)  # emits an 'rg' operator -> DeviceRGB
    c.rect(bleed + 10, bleed + 10, 40, 40, fill=1, stroke=0)
    c.showPage()
    c.save()
    _finalize(dest, keep_helvetica=False, pdfx=True, output_intent=True)


def _make_lowres_pdf(dest: Path) -> None:
    w, h, bleed, page_w, page_h = _page_size_pt()
    c = canvas.Canvas(str(dest), pagesize=(page_w, page_h))
    c.setTrimBox((bleed, bleed, bleed + w, bleed + h))
    c.setBleedBox((0, 0, page_w, page_h))
    c.setFillColorCMYK(0, 0, 0, 1)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # 300x300px placed at 2x2in => 150ppi (below the 200ppi fail floor).
    # Grayscale so this fixture isolates the ppi issue -- an RGB source
    # image would also (correctly) trip the color-space check.
    img_path = dest.parent / f"_src_{dest.stem}.png"
    Image.new("L", (300, 300), 128).save(img_path)
    c.drawImage(str(img_path), bleed + 10, bleed + 10, width=144, height=144)
    c.showPage()
    c.save()
    os.remove(img_path)
    _finalize(dest, keep_helvetica=False, pdfx=True, output_intent=True)


def _make_font_not_embedded_pdf(dest: Path) -> None:
    w, h, bleed, page_w, page_h = _page_size_pt()
    c = canvas.Canvas(str(dest), pagesize=(page_w, page_h))
    c.setTrimBox((bleed, bleed, bleed + w, bleed + h))
    c.setBleedBox((0, 0, page_w, page_h))
    c.setFillColorCMYK(0, 0, 0, 1)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)
    c.setFillColorCMYK(0, 0, 0, 0)
    c.setFont("Helvetica", 14)  # a standard font, never embedded
    c.drawString(bleed + 10, bleed + 10, "Not embedded")
    c.showPage()
    c.save()
    _finalize(dest, keep_helvetica=True, pdfx=True, output_intent=True)


def _make_no_bleedbox_pdf(dest: Path) -> None:
    w, h, bleed, page_w, page_h = _page_size_pt()
    c = canvas.Canvas(str(dest), pagesize=(page_w, page_h))
    c.setTrimBox((bleed, bleed, bleed + w, bleed + h))
    # deliberately no setBleedBox
    c.setFillColorCMYK(0, 0, 0, 1)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)
    c.showPage()
    c.save()
    _finalize(dest, keep_helvetica=False, pdfx=True, output_intent=True)


def _make_no_pdfx_pdf(dest: Path) -> None:
    w, h, bleed, page_w, page_h = _page_size_pt()
    c = canvas.Canvas(str(dest), pagesize=(page_w, page_h))
    c.setTrimBox((bleed, bleed, bleed + w, bleed + h))
    c.setBleedBox((0, 0, page_w, page_h))
    c.setFillColorCMYK(0, 0, 0, 1)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)
    c.showPage()
    c.save()
    _finalize(dest, keep_helvetica=False, pdfx=False, output_intent=False)


def _make_multipage_pdf(dest: Path) -> None:
    w, h, bleed, page_w, page_h = _page_size_pt()
    c = canvas.Canvas(str(dest), pagesize=(page_w, page_h))
    for _ in range(2):
        c.setTrimBox((bleed, bleed, bleed + w, bleed + h))
        c.setBleedBox((0, 0, page_w, page_h))
        c.setFillColorCMYK(0, 0, 0, 1)
        c.rect(0, 0, page_w, page_h, fill=1, stroke=0)
        c.showPage()
    c.save()
    _finalize(dest, keep_helvetica=False, pdfx=True, output_intent=True)


# -- TIFF fixtures ---------------------------------------------------------


def _tiff_dims_px(spec: dict = A5, ppi: float = 150) -> tuple[int, int]:
    mm_per_in = 25.4
    w_px = round((spec["w_mm"] + 2 * spec["bleed_mm"]) / mm_per_in * ppi)
    h_px = round((spec["h_mm"] + 2 * spec["bleed_mm"]) / mm_per_in * ppi)
    return w_px, h_px


def _make_good_tiff(dest: Path) -> None:
    w_px, h_px = _tiff_dims_px()
    img = Image.new("CMYK", (w_px, h_px), (0, 0, 0, 255))
    img.save(dest, format="TIFF", dpi=(150, 150))


def _make_wrong_mode_tiff(dest: Path) -> None:
    w_px, h_px = _tiff_dims_px()
    img = Image.new("RGB", (w_px, h_px), (200, 30, 30))
    img.save(dest, format="TIFF", dpi=(150, 150))


# -- PNG fixtures -----------------------------------------------------------


def _make_good_png(dest: Path) -> None:
    Image.new("RGB", (1080, 1350), (30, 60, 120)).save(dest, format="PNG")


def _make_wrong_dims_png(dest: Path) -> None:
    Image.new("RGB", (500, 500), (30, 60, 120)).save(dest, format="PNG")


def _make_unwanted_alpha_png(dest: Path) -> None:
    Image.new("RGBA", (1080, 1350), (30, 60, 120, 128)).save(dest, format="PNG")


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/generated")
    build_all(out)
    print(f"Fixtures written to {out}")
