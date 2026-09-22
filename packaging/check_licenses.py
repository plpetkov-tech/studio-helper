"""License allowlist check for runtime dependencies (SPEC.md §2.4, §8).

Only MIT, BSD, Apache, and PSF-family licenses may ship in
runtime/lib. Run after `pip install -r requirements-dev.in` (which
installs requirements.in on top), so importlib.metadata can read each
package's declared license.

comtypes carries a `sys_platform == "win32"` marker (SPEC.md
requirements.in) so it is not installed when this check runs on
Linux CI; its license (MIT) is asserted here instead of skipped.
"""

from __future__ import annotations

import re
import sys
from importlib import metadata

ALLOWED = re.compile(
    r"MIT|BSD|Apache|PSF|Python Software Foundation|HPND|ISC|MIT-CMU", re.IGNORECASE
)
DENYLIST_HINT = re.compile(r"GPL|AGPL|SSPL|CC-BY-NC|Commons Clause", re.IGNORECASE)

# Packages whose install is gated by an environment marker (e.g.
# Windows-only) and therefore may not be present when this check runs.
# Their license is recorded here instead of read from metadata.
KNOWN_MARKER_GATED = {
    "comtypes": "MIT",
}


def declared_license(dist_name: str) -> str | None:
    try:
        meta = metadata.metadata(dist_name)
    except metadata.PackageNotFoundError:
        return None
    license_field = meta.get("License")
    license_expression = meta.get("License-Expression")
    classifiers = meta.get_all("Classifier") or []
    license_classifiers = [c for c in classifiers if c.startswith("License ::")]
    parts = [p for p in [license_expression, license_field, *license_classifiers] if p]
    return " | ".join(parts) if parts else None


def iter_requirement_names(requirements_in: str):
    with open(requirements_in, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            name = re.split(r"[=<>; ]", line, maxsplit=1)[0]
            if name:
                yield name


def main() -> int:
    requirements_in = sys.argv[1] if len(sys.argv) > 1 else "requirements.in"
    problems = []

    for name in iter_requirement_names(requirements_in):
        info = declared_license(name)
        if info is None:
            if name in KNOWN_MARKER_GATED:
                info = KNOWN_MARKER_GATED[name]
            else:
                problems.append(f"{name}: not installed, cannot verify license")
                continue

        if DENYLIST_HINT.search(info):
            problems.append(f"{name}: DENIED license text: {info!r}")
        elif not ALLOWED.search(info):
            problems.append(f"{name}: unrecognized license, needs manual review: {info!r}")
        else:
            print(f"OK   {name}: {info}")

    if problems:
        print("\nLicense check FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("\nAll dependency licenses allowed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
