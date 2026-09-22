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
import threading
import urllib.request

from studio_helper.server import create_server


def _check_imports() -> list[str]:
    problems = []
    for mod in ("yaml", "jsonschema", "pypdf", "pypdfium2", "PIL"):
        try:
            __import__(mod)
        except ImportError as exc:
            problems.append(f"{mod}: {exc}")
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
