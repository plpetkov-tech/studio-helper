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

## Repo layout

```
app/studio_helper/   the Python package (stdlib HTTP server + local web UI)
adobe/                Illustrator/Photoshop ExtendScript adapters (ES3)
figma-plugin/         Figma plugin (TypeScript)
defaults/registry.yaml default format registry (placeholders until §13 is filled in)
tests/                 pytest suite; tests/adobe requires STUDIO_HELPER_ADOBE=1
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
pytest -q
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

## Status

Building one milestone at a time (SPEC.md §12), each as its own PR.
See SPEC.md §15 for what's been decided along the way, and §13 for
the open items still waiting on values from the studio (bleed,
LED/web/IG sizes, panel gaps, a rejected print sample, etc.) — the
print and digital generators stay on placeholder values until those
land.
