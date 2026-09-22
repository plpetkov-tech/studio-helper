"""Emit a minimal CycloneDX SBOM for the runtime dependencies bundled
into runtime/lib (SPEC.md §5.1, §8).

Usage: python generate_sbom.py <requirements.lock> <app_version> > SBOM.cdx.json
"""

from __future__ import annotations

import datetime
import json
import re
import sys

LINE_RE = re.compile(
    r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-]+)(?:\s*;\s*[^\\]+)?\s*\\?\s*$"
)
HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})")


def parse_lock(path: str) -> list[dict]:
    components = []
    name = None
    version = None
    hashes: list[str] = []

    def flush():
        if name and version:
            components.append({"name": name, "version": version, "hashes": hashes[:]})

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.strip().startswith("#"):
                continue
            m = LINE_RE.match(line.strip())
            if m:
                flush()
                name, version = m.group(1), m.group(2)
                hashes = []
                continue
            h = HASH_RE.search(line)
            if h:
                hashes.append(h.group(1))
    flush()
    return components


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: generate_sbom.py <requirements.lock> <app_version>", file=sys.stderr)
        return 2

    lock_path, app_version = sys.argv[1], sys.argv[2]
    components = parse_lock(lock_path)

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.datetime.now(datetime.UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "component": {
                "type": "application",
                "name": "studio-helper",
                "version": app_version,
            },
        },
        "components": [
            {
                "type": "library",
                "name": c["name"],
                "version": c["version"],
                "purl": f"pkg:pypi/{c['name']}@{c['version']}",
                "hashes": [{"alg": "SHA-256", "content": h} for h in c["hashes"]],
            }
            for c in components
        ],
    }

    print(json.dumps(sbom, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
