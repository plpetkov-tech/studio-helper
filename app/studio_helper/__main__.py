"""Entry point: `python -m studio_helper` (SPEC.md §5.1, §6.2).

Normal launch: seed user data, hand off to a live instance if one
exists, otherwise start the server and open the browser. `--selftest`
proves the packaged app runs with no external installs (SPEC.md §9).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import threading
import webbrowser
from pathlib import Path

from studio_helper import config, instance, logging_setup, paths
from studio_helper.api.context import AppContext
from studio_helper.poller import Poller
from studio_helper.server import create_server

# SHA-256 (LF-normalised) of every bundled registry.yaml a release has
# shipped. A user registry matching one of these was never edited, so
# it is safe to replace with the newer bundled default on startup.
PREVIOUS_DEFAULT_REGISTRY_HASHES = frozenset({
    "b6eb82677aabd97cfa21d04dcdf9c0798ad6c01e27091a3319f68d4f9cfa8113",  # M0 placeholder
})


def _normalised_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def seed_user_registry() -> None:
    dest = paths.user_registry_path()
    src = paths.bundled_registry_path()
    if not src.exists():
        return
    if dest.exists():
        if _normalised_hash(dest) not in PREVIOUS_DEFAULT_REGISTRY_HASHES:
            return
        if _normalised_hash(dest) == _normalised_hash(src):
            return
        shutil.copyfile(dest, dest.with_suffix(".yaml.bak"))
    paths.ensure_app_data_dirs()
    shutil.copyfile(src, dest)


def run() -> int:
    logger = logging_setup.setup()
    logger.info("Studio Helper starting")

    live = instance.find_live_instance()
    if live is not None:
        logger.info("Live instance found on port %s, handing off", live.port)
        webbrowser.open(live.url())
        return 0

    instance.clear()
    seed_user_registry()
    cfg = config.Config.load()
    poller = Poller(Path(cfg.jobs_root))
    ctx = AppContext(cfg, poller=poller)

    server = create_server(ctx=ctx)
    host, port = server.server_address[:2]
    info = instance.InstanceInfo(port=port, token=server.token, pid=os.getpid())
    instance.write(info)
    logger.info("Serving on http://127.0.0.1:%s", port)

    poller.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    webbrowser.open(info.url())

    try:
        thread.join()
    except KeyboardInterrupt:
        server.shutdown()
    finally:
        poller.stop()
        instance.clear()
        server.server_close()

    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if "--selftest" in argv:
        from studio_helper import selftest

        return selftest.run()

    return run()


if __name__ == "__main__":
    sys.exit(main())
