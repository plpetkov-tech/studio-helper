# Studio Helper

Automates the setup, naming, folders, preflight, and export around
print and digital design work for an in-house graphic designer — never
the design itself. Full spec: [SPEC.md](SPEC.md). Built milestone by
milestone; current status and decisions are logged in
[SPEC.md §15](SPEC.md#15-decisions).

Ships as a zip from a GitHub Release: extract, double-click
`Start Studio Helper.bat`, no installer, no admin rights, fully
offline. See `README.txt.template` for the end-user instructions that
ship inside the zip.

What it does in v1.1:

- **Files & export**: job folders, Illustrator/Photoshop/Figma setup at
  every size, preflight, export with the delivery names, a live ✓/✕
  check of every exported file (PDF, TIFF, PNG, JPG, MP4).
- **One master, cut to every size** (v1.1): she designs once on a master
  artboard in Illustrator (every size, print included) or Photoshop
  (digital sizes), marks what must stay with a box, and the app cuts it:
  digital sizes into `04_export` (Pillow), print sizes placed and linked
  into her Illustrator print file (`cut_master.jsx`).
- **Campaigns that grow**: add sizes to a finished job (new artboards
  start from the closest existing artwork), reuse a campaign as a new
  job, revisions, campaign dates.
- **Video**: every video size made through the designer's own Concat,
  either from her statics (Figma-style motion: feel, camera move,
  transitions, brand pieces coming in) or from one Higgsfield video
  fitted to every screen around a "juice box", with a live in-browser
  preview of exactly what will be rendered.
- **Deliver**: one ZIP per job (or per batch of added sizes) for the
  manager, with a README of the print-shop notes.
- **Assistant access**: an MCP server (`python -m studio_helper --mcp`)
  that ChatGPT desktop uses; the app registers it in ChatGPT's
  `~/.codex/config.toml` itself.

The feature plan and its history are in `ROADMAP.md` (kept out of the
public repository, like `AGENTS.md`).

## Repo layout

```
app/studio_helper/   the Python package (stdlib HTTP server + local web UI)
adobe/                Illustrator/Photoshop ExtendScript adapters (ES3)
figma-plugin/         Figma plugin (TypeScript)
defaults/registry.yaml default format registry (the studio's real formats; some sizes marked estimated)
tests/                 pytest suite; tests/adobe/check_*.js run the JSX adapters in Node with mocked apps;
                       tests/web/check_motion_js.js checks the video preview's math against the renderer's
packaging/             release assembly (build_release.ps1) and lock-file tooling
.github/workflows/     ci.yml (every push/PR), release.yml (on tag v*)
```

## Dev setup

Requires Python 3.12+ locally (the shipped app bundles its own
embeddable Python — this is only for development).

```sh
python -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows
pip install -r requirements-dev.in
```

Run the app:

```sh
PYTHONPATH=app python -m studio_helper
```

Run the test suite:

```sh
pytest -q -m "not adobe"
for f in tests/adobe/check_*.js; do node "$f"; done   # JSX adapters, mocked apps
node tests/web/check_motion_js.js                      # video preview math
node tests/web/check_master_js.js                      # master cut preview == the cut
node tests/adobe/check_master_jsx.js                   # master scripts, mocked Illustrator/Photoshop
STUDIO_HELPER_CONCAT=1 pytest -q tests/unit/test_video_render.py -k real   # with Concat installed
```

Lint:

```sh
ruff check app tests packaging
```

Self-test (same check the packaged release runs against the extracted
zip — see `packaging/build_release.ps1`):

```sh
PYTHONPATH=app python -m studio_helper --selftest
```

## Dependency locking

`requirements.in` lists the runtime deps that ship inside the
release zip. `requirements.lock` pins them (and their transitive
deps) to exact `win_amd64`/CPython-3.12 wheels with SHA256 hashes,
because the release build uses `pip install --require-hashes`
(SPEC.md §5.1, §8). Regenerate it with:

```sh
packaging/lock_requirements.sh
```

then merge the printed hashes into `requirements.lock` by hand (it
prints a diff-friendly list, it does not overwrite the file, so any
version bump is a visible, reviewable change).

## Building a release locally

Requires Windows with PowerShell, plus Python 3.12 and Node 20 on
PATH (the same tools `release.yml` uses):

```powershell
pwsh packaging/build_release.ps1 -Version 0.1.0
```

Produces `dist/StudioHelper-v0.1.0.zip`, `dist/SBOM.cdx.json`, and
`dist/SHA256SUMS`, and smoke-tests the extracted zip with
`--selftest` before finishing.

## Releasing

1. Commit with the version in the title, e.g. `... (v0.5.1)`, and
   bump `__version__` in `app/studio_helper/__init__.py` to match.
   (The release build stamps the tag's version into the zip either way.)
2. Push `main` and wait for CI to pass. Pushes that change
   `.github/workflows/` need a token with the `workflow` scope, or SSH.
3. Push the annotated tag `vX.Y.Z`. `release.yml` builds and publishes
   the zip, `SHA256SUMS` and the SBOM; it doesn't wait for CI itself.
4. The designer installs it with ? → Check for updates.

## Status

In daily use. The milestones in SPEC.md §12 are built; changes since
then come from real use and are logged, newest last, in SPEC.md §15.
