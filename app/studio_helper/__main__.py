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

from studio_helper import config, instance, logging_setup, paths, updater
from studio_helper.api.context import AppContext
from studio_helper.core import default_formats
from studio_helper.poller import Poller
from studio_helper.server import create_server

# SHA-256 (LF-normalised) of every bundled registry.yaml a release has
# shipped. A user registry matching one of these was never edited, so
# it is safe to replace with the newer bundled default on startup.
PREVIOUS_DEFAULT_REGISTRY_HASHES = frozenset({
    "b6eb82677aabd97cfa21d04dcdf9c0798ad6c01e27091a3319f68d4f9cfa8113",  # M0 placeholder
    "ed5579a6600b7b82819d68108db045f9235be9d42f26af00129d284744043ecb",  # v0.3.2 mall formats
    "4fa2719948aba76320cd3b0571c1cfabca09fee2030f5aabf0f2129f4ff05c5a",  # v0.3.6 IDEA Comm formats
    "608fd2cad608d3060201e7d9d89b212d61d6d88f323eda28902e7d65ed3f87f7",  # v0.4.0 groups, notes
    "d4694699db88d25832b2c779896bfe33f96d1df82debeda3896e27556e953063",  # v0.4.2 built-in PDF/X-1a
    "dc75356771ba456d5e9408766049aaaa70e4b2467eaaee961c4c0d0d7a60b9ba",  # v0.4.3 banner pair
    "eff0e7948427baf965787c2b646e3a0395b2e22226852780f555053e7e98c729",  # v0.4.5 60 ppi IDEA vinyls
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


def sync_figma_plugin() -> None:
    src = paths.bundled_root() / "figma-plugin"
    if not (src / "manifest.json").exists():
        return
    dest = paths.figma_plugin_dir()
    for rel in ("manifest.json", "ui.html", "dist/code.js"):
        if (src / rel).exists():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src / rel, dest / rel)


def merge_default_formats() -> list[str]:
    """New default formats reach a registry she has edited too."""
    return default_formats.merge_new_defaults(
        paths.user_registry_path(), paths.bundled_registry_path(),
        paths.app_data_dir() / "default_formats_seen.json",
    )


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
    try:
        sync_figma_plugin()
    except OSError:
        logger.exception("Could not copy the Figma plugin")
    try:
        added = merge_default_formats()
        if added:
            logger.info("Added new default formats to the registry: %s", ", ".join(added))
    except OSError:
        logger.exception("Could not add new default formats")
    try:
        for folder in updater.cleanup_old_installs(paths.bundled_root()):
            logger.info("Removed old install %s", folder)
    except OSError:
        logger.exception("Could not clean up old installs")
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
