"""`python -m studio_helper --selftest` (SPEC.md §9).

Proves the packaged app runs with no external installs: imports the
bundled dependencies, starts the server on a random port, and hits
/api/health. Exits 0 on success, 1 otherwise. Never raises past
`run()` -- packaging smoke tests treat a non-zero exit as the failure
signal, not a traceback.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

from studio_helper.server import create_server


def _check_imports() -> list[str]:
    problems = []
    for mod in ("yaml", "jsonschema", "pypdf", "pypdfium2", "PIL"):
        try:
            __import__(mod)
        except ImportError as exc:
            problems.append(f"{mod}: {exc}")
    return problems


def _check_registry() -> list[str]:
    from studio_helper import paths
    from studio_helper.core.registry import RegistryError, load_registry

    try:
        load_registry(paths.bundled_registry_path())
    except RegistryError as exc:
        return [f"default registry: {exc}"]
    return []


def _check_validators() -> list[str]:
    """Runs each validator on a tiny fixture built from only the
    bundled runtime deps (pypdf + Pillow -- reportlab is dev-only and
    is never shipped), proving the validator code paths actually
    import and execute in the packaged app."""
    problems: list[str] = []
    try:
        import pypdf
        from PIL import Image

        from studio_helper.validators import pdf as pdf_validator
        from studio_helper.validators import raster

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            png_path = tmp_path / "mini.png"
            Image.new("RGB", (10, 10), "red").save(png_path)
            png_fmt = {
                "id": "x", "kind": "social", "size": {"w": 10, "h": 10, "unit": "px"},
                "allow_alpha": False,
            }
            png_checks = raster.validate(
                png_path,
                png_fmt,
                {"format_id": "x", "type": "png", "panel": None, "expected_stem": "mini"},
            )
            if not png_checks:
                problems.append("raster validator returned no checks")

            pdf_path = tmp_path / "mini.pdf"
            writer = pypdf.PdfWriter()
            writer.add_blank_page(width=72, height=72)
            with open(pdf_path, "wb") as f:
                writer.write(f)
            pdf_checks = pdf_validator.validate(
                pdf_path,
                {
                    "id": "y", "kind": "print", "size": {"w": 25.4, "h": 25.4, "unit": "mm"},
                    "bleed_mm": 0, "min_image_ppi": {}, "scale": 1,
                },
                {"format_id": "y", "type": "pdf", "panel": None, "expected_stem": "mini"},
            )
            if not pdf_checks:
                problems.append("pdf validator returned no checks")
    except Exception as exc:  # noqa: BLE001 - selftest reports, never raises
        problems.append(f"validator check failed: {exc}")
    return problems


def _check_server() -> list[str]:
    problems = []
    server = create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/health",
            headers={"Host": f"127.0.0.1:{port}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ok"):
                problems.append(f"/api/health returned {data!r}")
    except Exception as exc:  # noqa: BLE001 - selftest reports, never raises
        problems.append(f"server check failed: {exc}")
    finally:
        server.shutdown()
        server.server_close()
    return problems


def run() -> int:
    problems: list[str] = []
    problems += _check_imports()
    problems += _check_registry()
    problems += _check_validators()
    problems += _check_server()

    if problems:
        print("Studio Helper selftest FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("Studio Helper selftest OK")
    return 0


if __name__ == "__main__":
    sys.exit(run())
