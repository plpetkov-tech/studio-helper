# Studio Helper — Build Spec (v1: Phases 0–2)

> Audience: Claude Code (implementer) and the repo owner.
> Build milestone by milestone (§12). Do not invent format specs. Every value marked `TBD` comes from the owner.

---

## 1. Context

**User.** An in-house graphic designer at a fashion brand. She is not a programmer. She uses Windows, the latest Adobe Illustrator and Photoshop, and Figma Pro (desktop app).

**Workload.** 30–40 jobs per week. A typical campaign has about 25 outputs:
- A4/A5/A6 print flyers
- about 10 LED screen sizes (PNG or MP4)
- 9 web banners (PNG)
- IG posts and stories

**Pain points.**
- Setting up documents correctly: bleed, color mode, sizes
- Resizing to every format
- Exporting with correct settings and names

Print jobs have been rejected because the background did not extend into the bleed. Feedback reaches her through her manager, so every mistake costs hours.

**Tool roles.**
- Print is always designed in **Illustrator**.
- Digital (LED, web, social) is designed in **Photoshop or Figma**. She chooses per job, so both must be supported.

**Goal.** Automate everything around the creative work: document setup, naming, folders, preflight and export. **Never automate the design itself.**

## 2. Hard constraints

1. **Distributed as a zip from a GitHub Release. Extract, double-click, it runs.**
   - No installer.
   - No admin rights.
   - No system Python, Node, or other prerequisites.
2. User-level only. Write only to the extracted folder, `%APPDATA%`, `%LOCALAPPDATA%`, `%TEMP%`, and the jobs folder. HKCU registry keys are allowed only if strictly needed; none are currently needed.
3. Runs **fully offline**. There is no telemetry and client files never leave the machine. The one deliberate exception is self-update (§15, 2026-09-24): a GET to GitHub's release API/CDN, made only when she clicks "Check for updates" / "Download & install," never automatically. No client data is ever sent.
4. Only permissively licensed dependencies (MIT, BSD, Apache, PSF). **Do not use PyMuPDF** (it is AGPL).
5. Plain-language UI and messages. No stack traces in the UI; send them to the log file.
6. The tool must **never overwrite or delete her working files** (`.ai`, `.psd`).

## 3. Non-goals for v1

- No design templates, layout auto-adaptation, or promo kits (Phase 3+).
- No video validation or rendering (the MP4 validator is a stub).
- No job/brief tracker and no publishing to IG or the web.
- No auto-updater.

## 4. Architecture

```
Studio Helper (embedded Python, local web UI on 127.0.0.1)
│
├─ registry.yaml ─► core: registry, job model, naming, folder scaffold
│                        │
│   "New Job" ─► <jobs_root>/<date>_<slug>/job.json + folder tree
│                        │
│    ┌───────────────────┼──────────────────────────┐
│    ▼ COM DoJavaScript  ▼ COM DoJavaScript         ▼ she loads job.json in plugin
│  Illustrator .jsx    Photoshop .jsx             Figma plugin (TS → dist/)
│  print docs + export digital PSD + export       digital frames + export
│    └───────────────────┬──────────────────────────┘
│                        ▼
│   poller on 04_export/ ─► validators (pdf / tiff / png|jpg) ─► report
```

**Design principles.**
- **Python is the brain and the single writer of `job.json`.** The JSX and Figma adapters are thin. They receive specs, act inside the app, and return JSON. They contain no business rules beyond geometry.
- **Validate outputs, not apps.** Exported files are the source of truth. The same validators run no matter which app produced the file.
- **Every JSX also runs standalone** from `File › Scripts › Other Script…` (it prompts for `job.json`). This is the fallback when COM fails.

## 5. Distribution and runtime

### 5.1 Release zip layout

```
StudioHelper-vX.Y.Z/
  Start Studio Helper.bat        # start "" "%~dp0runtime\pythonw.exe" -m studio_helper
  README.txt                     # plain-language, for her (see 5.4)
  runtime/                       # Python 3.12.x embeddable (win amd64), pinned
    python312._pth               # edited: adds ..\app and lib, enables `import site`
    lib/                         # third-party deps (pip --target)
  app/studio_helper/             # Python package
  adobe/illustrator/*.jsx
  adobe/illustrator/lib/json2.js
  adobe/photoshop/*.jsx
  adobe/presets/StudioHelper_X1a.joboptions   # TBD: must match print dept settings
  figma-plugin/manifest.json, code.js, ui.html
  defaults/registry.yaml
  LICENSES/, SBOM.cdx.json
```

**Embeddable Python notes.**
- It has **no tkinter and no pip**. This is why the UI is a local web UI (§6.2).
- Dependencies are installed in CI with a full CPython of the *same minor version*, using `pip install --target runtime/lib --require-hashes -r requirements.lock`.

**Runtime dependencies.** Pin all of them, with hashes:

| Package | Purpose |
|---|---|
| `pyyaml` | registry |
| `jsonschema` | registry validation |
| `pypdf` | PDF structure: boxes, OutputIntents, fonts |
| `pypdfium2` | PDF rendering with alpha, image placement/DPI |
| `Pillow` | raster validation |
| `comtypes` | pure-Python COM; avoids pywin32's DLL/postinstall issues in embedded Python |

Use only the stdlib for the HTTP server and the file poller.

### 5.2 User data (survives updates)

`%APPDATA%\StudioHelper\` contains:
- `config.json` (jobs_root, registry_path, last_opened_jobs)
- `registry.yaml` (copied from `defaults/` on first run; **never overwritten afterwards**)
- `instance.json` (port and token of the running instance)
- `logs/` (rotating, 5 × 1 MB)

The default `jobs_root` is `%USERPROFILE%\Documents\Studio Jobs`.

Updating means extracting the new zip anywhere and running it. If the bundled default registry has a higher `version` than hers, show a notice with a diff. Never merge automatically.

### 5.3 First run and the "Setup check" page

1. Create the user data dirs and seed `registry.yaml`.
2. Install `StudioHelper_X1a.joboptions` into `%APPDATA%\Adobe\Adobe PDF\Settings\`. If a file there has the same name but a different hash, back it up first.
3. Show the Setup check page, with ✓/✗ and a fix hint for each item:
   - Illustrator reachable via COM
   - PDF preset visible to Illustrator (a JSX checks `app.PDFPresetsList`)
   - Photoshop reachable via COM
   - Jobs folder writable
   - Registry valid
   - Figma plugin import instructions, with a button that opens `figma-plugin/` in Explorer
4. Warn if the app's own files carry Mark-of-the-Web (`<file>:Zone.Identifier` exists), and point to the README "Unblock" step.

### 5.4 README.txt (for her)

Short and plain. It covers:
- Right-click the zip → Properties → **Unblock** → Extract.
- Double-click `Start Studio Helper`.
- One-time Figma setup: Figma desktop › Plugins › Development › Import plugin from manifest… › pick `figma-plugin\manifest.json`.
- What to do if Illustrator automation fails (the manual script path).

## 6. Components

### 6.1 Data model

**`registry.yaml`.** Validate it against `app/studio_helper/schema/registry.schema.json`.

```yaml
version: 1
print_defaults:
  bleed_mm: 3                    # TBD
  safe_mm: 5                     # TBD
  pdf_preset: StudioHelper_X1a
  raster_ppi: 300
  min_image_ppi: {warn: 300, fail: 200}
  tiff_if_longest_side_mm_over: TBD
  tiff_ppi: TBD                  # at final physical size
formats:
  - id: flyer-a5                 # kebab-case, unique
    name: A5 flyer
    kind: print                  # print | screen | web | social
    size: {w: 148, h: 210, unit: mm}
    # optional: bleed_mm, safe_mm, scale (e.g. 0.1 for vinyl), exports override
    exports: [pdf]               # print: pdf|tiff (auto-switch by threshold); digital: png|jpg|mp4
  - id: elevator-main
    name: Elevator doors (main lobby)
    kind: print
    panels:                      # multi-panel piece designed as one spread
      - {w: TBD, h: TBD}
      - {w: TBD, h: TBD}
    panel_gap_mm: TBD
    unit: mm
    exports: [pdf]
  - id: led-mall-entrance
    name: LED mall entrance
    kind: screen
    size: {w: 384, h: 1920, unit: px}
    safe_px: 0
    exports: [png, mp4]
    allow_alpha: false
job_types:
  full-campaign: [flyer-a4, flyer-a5, flyer-a6, "led-*", "web-*", "ig-*"]
  shop-promo:    [flyer-a4, "led-*", "ig-story"]
```

Registry rules:
- `print` formats use `mm`. Other kinds use `px`.
- Glob patterns in `job_types` are resolved at job creation.
- Unknown keys are an error. The error message names the file and line.

**`job.json`.** Python is the only writer.

```json
{
  "schema_version": 1,
  "id": "2026-09-25_autumn-sale",
  "name": "Autumn Sale",
  "slug": "autumn-sale",
  "created": "2026-09-25T15:02:11+03:00",
  "registry_version": 1,
  "version": 1,
  "formats": [ /* fully resolved copies of registry entries incl. defaults */ ],
  "files": {"print": ["03_working/..._print_v01.ai"], "psd": null},
  "deliverables": [
    {"format_id": "flyer-a5", "type": "pdf", "panel": null,
     "expected_stem": "2026-09-25_autumn-sale_flyer-a5_148x210mm_v01"}
  ]
}
```

**Naming.**
- Pattern: `{date}_{slug}_{format-id}_{W}x{H}{unit}[_p{n}]_v{NN}.{ext}`.
- The date is the job creation date. The slug is ASCII kebab-case, max 40 characters, transliterated (she may type Bulgarian Cyrillic, so `Есенна разпродажба` becomes `esenna-razprodazhba`).
- "Start revision" in the UI increments `version`. New exports get `v02`. Older files are kept.

**Folder scaffold.**

```
<date>_<slug>/
  job.json  report.html
  01_brief/  02_assets/  03_working/
  04_export/print/  04_export/led/  04_export/web/  04_export/social/
```

Export subfolders map from kind: `print` goes to `print`, `screen` to `led`, `web` to `web`, and `social` to `social`.

### 6.2 Local web UI

**Server.**
- Stdlib `ThreadingHTTPServer`, bound to **127.0.0.1** on a random free port.
- A per-launch random token, required as a header on every API call.
- Check the `Host` header (anti-DNS-rebinding). No CORS headers.
- The launcher opens the default browser at `http://127.0.0.1:<port>/#token=…`.
- Single instance: if `instance.json` points to a live server, open the browser there and exit.
- A "Quit" button shuts the server down.

**Frontend.** Vanilla HTML/CSS/JS served from the package, with no CDN or network dependencies. Keep it calm, clear, and large-targeted.

**Screens.**
1. **Home.**
   - A "New Job" button.
   - Recent jobs as cards, each with a deliverables progress bar (e.g. 18/25 ✓).
   - A "Open existing job folder…" option.
2. **New Job.**
   - Name, a job type dropdown, and a format checklist. The job type pre-ticks formats; she can add or remove.
   - A live preview of folder and file names.
   - Create.
3. **Job page.**
   - Header buttons: Open folder, Start revision (vN→vN+1).
   - **Print:**
     - "Create Illustrator print file"
     - "Check print file" (preflight only)
     - "Check & export print"
   - **Digital:**
     - "Create Photoshop file"
     - "Export from Photoshop"
     - A **Figma** panel with numbered steps and a "Copy job.json path" button.
   - **Deliverables table.** One row per deliverable: expected name, found file, status ✓/⚠/✗. Expanding a row shows its checks, each with a plain-language hint.
4. **Registry.**
   - Read-only table of formats.
   - "Open registry file" (in Notepad).
   - "Validate registry".
5. **Setup check** (§5.3).

**API.** JSON over `/api/...`, one endpoint per action. Long actions (COM calls) run in a worker thread; the UI polls `/api/tasks/<id>`.

### 6.3 Adobe bridge (Python, `comtypes`)

**Connecting.** Use `comtypes.client.GetActiveObject("Illustrator.Application")`, falling back to `CreateObject(..., dynamic=True)`. Photoshop works the same way with `Photoshop.Application`. Allow a 120 s timeout for app launch.

**Invocation protocol.** Avoid passing COM argument arrays:

```python
code = f'var SH_ARGS = {json.dumps(args)}; $.evalFile({json.dumps(jsx_path_forward_slashes)});'
result = app.DoJavaScript(code)
```

- The JSX file's last expression is `JSON.stringify(result)`.
- The result is always `{"ok": bool, "data": {...}, "errors": [{"code","message","hint"}], "warnings": [...]}`.

**Dialogs.** Illustrator dialogs block COM. Every Illustrator JSX sets `app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS` and restores it in `finally`. Photoshop: `app.displayDialogs = DialogModes.NO`, restored in `finally`.

**When COM fails** (not installed, permission issue, timeout), the UI shows the manual path:
1. Click "Open scripts folder".
2. In Illustrator: File › Scripts › Other Script… › `new_print_doc.jsx`.
3. Select `job.json` when asked.

### 6.4 Illustrator adapters (ExtendScript, **ES3 only**)

The environment is ES3: no `let`/`const`, no arrow functions, no `Array.prototype.map`/`forEach`/`indexOf`, no native `JSON`. Include `lib/json2.js` via `#include`. Shared helpers go in `lib/common.jsx`: mm↔pt (1 mm = 2.834645669 pt), result envelope, args-or-dialog.

**`new_print_doc.jsx`** — input: `{job, output_dir}`.
- Takes print formats only. Groups them by effective bleed, because Illustrator bleed is document-wide. Each group becomes one document: `…_print_v01.ai`, or `…_print_bleed{N}mm_v01.ai` when there are several groups.
- `DocumentPreset` settings:
  - `colorMode = DocumentColorSpace.CMYK`
  - `units = RulerUnits.Millimeters`
  - `rasterResolution = DocumentRasterResolution.HighResolution`
  - `documentBleedLink = true`
  - `documentBleedOffsetRect` set from the bleed
  - `numArtboards = N`
- Artboards:
  - Set each `artboardRect` explicitly, as `[left, top, right, bottom]` in pt with top > bottom.
  - Lay them out left to right with `spacing = max(20mm, 2*bleed + 10mm)`.
  - Name each artboard with its format id (panels: `{id}_p{n}`).
- **Panels.** Place panel artboards side by side with the real `panel_gap_mm` between them, so a design can flow across doors. Add a guide rectangle for the gap.
- **Scale.** If `scale != 1`, the artboard size is the physical size × scale. Append `@1:{1/scale}` to the artboard name and record the scale in the result.
- **Canvas limit.** Illustrator's whole canvas is 5765 mm (227 in) square. Job creation (and "Create Illustrator print file" for older jobs) gives any print format over 5500 mm at scale 1 `scale: 0.1`. Artboards are shelf-packed into rows; a bleed group that doesn't fit one canvas is split into `_part1`, `_part2`, ... files. A single artboard still too big fails with a hint to lower `scale` and create a new job.
- **Layers,** top to bottom: `Guides` (locked), `Content`, `Background`. Draw safe-zone rectangles as guides on `Guides`.
- **Saving.** Save as `.ai` with PDF compatibility on. **Refuse to overwrite**: if the file exists, return `{ok:false, code:"EXISTS"}`, and the UI offers "Open existing".
- Returns: paths, artboard list, document settings.

**`preflight_export.jsx`** — input: `{job, ai_path, mode: "check"|"export", version, export_dir, force}`.

*Checks.* Each check returns `ok`, `warn`, or `fail`, plus a hint:
- The document is CMYK.
- Every artboard name maps to a job format, and every print deliverable has an artboard.
- Artboard size matches spec to within ±0.1 mm.
- Document bleed matches spec.
- **Bleed coverage heuristic.** For each artboard:
  1. Compute the bleed rect.
  2. Take the visible, unlocked-or-locked, non-guide items on the `Background` layer. If that layer is empty, use all visible non-guide items.
  3. Use `visibleBounds`. For a clipped group, use the group's bounds, which are the clip path's bounds.
  4. For each of the four edges, build the union of covered intervals along that edge, counting only items that reach the bleed line. Fail if any edge has a gap wider than 0.5 mm.
  5. Report which edges fail and where.
- Placed or raster items with an RGB color space: `warn` (PDF/X-1a will convert).
- Spot colors used: `warn`.
- Hidden layers that contain items: `warn`.

*Export.* Runs only if there are no `fail` results, or if `force` is true (the UI requires an explicit "Export anyway" confirmation).
1. `doc.save()` first.
2. For each artboard, decide the output type: TIFF if its longest physical side exceeds `tiff_if_longest_side_mm_over`, otherwise PDF.
3. **PDF.** Use `PDFSaveOptions` with `pDFPreset = print_defaults.pdf_preset` and `artboardRange = "<i>"`. Also set the bleed explicitly from the document bleed, to guard against the preset. Output goes to `04_export/print/<expected_stem>.pdf`.
   - Gotcha: **`saveAs` turns the open document into the PDF.** After the loop, close without saving and reopen the `.ai`.
4. **TIFF.** Use `ExportOptionsTIFF` with `imageColorSpace = CMYK`, resolution `tiff_ppi / scale`, `artBoardClipping = true`, `saveMultipleArtboards = true`, and `artboardRange = "<i>"`.
   - Gotcha: TIFF export clips to the artboard, dropping the bleed. So **temporarily expand `artboardRect` by the bleed, export, and restore it in `finally`**. Never leave the document modified.
5. Returns: the list of written files and all check results.

**`inspect.jsx`** — used by tests and Setup check. Returns the active or given document's state as JSON: color space, bleed, artboards (name and rect in mm), layers, `app.PDFPresetsList`.

### 6.5 Photoshop adapters (ExtendScript)

**`new_digital_doc.jsx`** — input: `{job, output_dir}`.
- Takes digital formats only.
- Creates an RGB, 8-bit, sRGB document at 72 ppi.
- Creates **one artboard per format** at exact pixel size, arranged in a grid with a 100 px gap, each named with its format id.
- Artboard creation needs Action Manager code. Generate the descriptor with ScriptListener or the Actions panel's "Copy as JavaScript", and wrap it in `makeArtboard(name, x, y, w, h)`.
- Saves `…_digital_v01.psd` and refuses to overwrite.

**`export_digital.jsx`** — input: `{job, psd_path, version, export_root}`.
- For each artboard that maps to a format:
  1. Duplicate the document.
  2. Keep only that artboard.
  3. Crop to its bounds and flatten. Keep transparency only if `allow_alpha`.
  4. Convert to sRGB.
  5. Export PNG or JPG to `04_export/<kind-dir>/<expected_stem>.<ext>`.
  6. Close the duplicate without saving.
- Never modifies the source PSD.

### 6.6 Figma plugin (TypeScript → `figma-plugin/`)

**Manifest.** `editorType: ["figma"]`, `networkAccess: {"allowedDomains": ["none"]}`, `documentAccess: "dynamic-page"`. Bundle with esbuild; commit nothing built, since CI builds it.

**UI.** A file input or drag-and-drop for `job.json`. The plugin cannot read the disk directly.

**"Create frames."**
- Creates a page named `{date} {job name}`.
- Adds one frame per digital deliverable at exact pixel size with a white fill.
- Arranges them in a grid.
- Adds a layout grid for the safe zone if `safe_px > 0`.
- **The frame name is the full export stem** (e.g. `2026-09-25_autumn-sale_led-mall-entrance_384x1920px_v01`). This way Figma's native Export produces correct filenames with zero plugin involvement. This is the primary export path.
- Idempotent: if the page exists, add only missing frames and never touch existing content.

**"Bump version."** Renames `_vNN` → `_vNN+1` on the frames of the current job page. The UI tells her to click "Start revision" in Studio Helper too.

**"Export all" (secondary).** `exportAsync({format:"PNG", constraint:{type:"SCALE", value:1}})` for each frame, zipped with `fflate` (bundled) and downloaded from the UI iframe. If download from the iframe proves unreliable in Figma desktop, drop this feature and rely on native export.

The Studio Helper poller auto-extracts `*.zip` files dropped into `04_export/` whose entries match the job's expected stems.

### 6.7 Validators (Python)

Every validator returns `FileResult{path, format_id, deliverable, status, checks:[Check{id,status,message,hint}]}`. The format and deliverable are derived by parsing the filename against the job's expected stems. Unknown files get `warn: "File name doesn't match any deliverable of this job."`

**PDF** (`pypdf` + `pypdfium2`):
- One page.
- TrimBox equals the format size to within ±0.2 mm. The BleedBox is the TrimBox plus the bleed on each side, ±0.2 mm.
- PDF/X-1a: `GTS_PDFXVersion` in Info or XMP, and `/OutputIntents` present.
- All fonts embedded: walk page and XObject-form resources for `/FontFile`, `/FontFile2`, or `/FontFile3`; Type3 fonts are OK.
- No DeviceRGB or 3-component ICC color spaces in content or images: `fail`.
- **Image ppi.** For each image object (pypdfium2), compute effective ppi = pixel size ÷ placed size in inches. Warn or fail against `min_image_ppi`, and report the image position.
- **Bleed coverage.** Render the page at 72 dpi with a transparent background (`fill_color=(0,0,0,0)`) and crop to the BleedBox. In the ring between TrimBox and BleedBox, fail if more than 0.1% of pixels have alpha < 250. Report the offending edges.

**TIFF** (Pillow):
- Mode is CMYK.
- Pixel dimensions equal (physical size + 2 × bleed) × `tiff_ppi`, to within ±2 px.
- The DPI tag is present.

**PNG/JPG** (Pillow):
- Exact pixel dimensions.
- Mode is RGB, or RGBA only if `allow_alpha`.
- The ICC profile is absent or sRGB. Warn on anything else, e.g. Display P3.
- Optional `max_kb` limit.

**MP4:** a stub that returns `warn: "Video checks not available yet."`

**Poller.**
- Scans `04_export/**` of jobs opened in the last 14 days, every 2 s.
- A file counts only once its size is unchanged for 2 consecutive scans.
- Re-validates on mtime change.
- Writes `report.html` (static, self-contained) in the job root and pushes status to the UI.

### 6.8 Deliverables matrix

Expected = each job format × each export type (× each panel), at the current `version`. Found = the file whose stem exactly matches. The UI and report show all expected rows, including missing ones as `✗ missing`. This matrix is her per-job checklist.

## 7. Error handling and UX rules

- Every action is idempotent and safe to repeat.
- Every error has three parts: what happened, why, and what to do. For example: "Background doesn't reach the bleed on the left and bottom of A5 flyer. Extend it 3 mm past the artboard edge."
- Never block on dialogs inside Adobe apps during automation.
- Log each action with inputs and results to `logs/`. The UI has a "Copy diagnostics" button that zips the logs and `job.json` for the owner.

## 8. Security

- Local-only server: 127.0.0.1, token, and Host check as described in §6.2.
- No outbound network calls, with one deliberate, user-initiated exception: `studio_helper.updater` (§15, 2026-09-24), which only ever runs from an explicit button click, never automatically -- `test_no_network.py` asserts both that `--selftest` never leaves loopback (monkeypatching `socket.create_connection`) and that it never calls the updater.
- **Path safety.**
  - All file operations resolve inside `jobs_root`, the app dir, or `%APPDATA%\StudioHelper`.
  - Reject `..` and absolute paths coming from the UI.
  - Sanitize slugs.
  - JSX paths are fixed, never taken from requests.
  - Values passed into `DoJavaScript` go through `json.dumps` only; never use string concatenation of user input.
- **Supply chain.**
  - `requirements.lock` with hashes, and `pip-audit` in CI.
  - GitHub Actions pinned by commit SHA.
  - The embeddable Python zip is downloaded by URL and pinned by SHA256.
  - A CycloneDX SBOM and `SHA256SUMS` are attached to each release.
  - A license allowlist check in CI.
- The Figma plugin has no network access.
- The repo must not contain client artwork. Real sample files live in `tests/fixtures/real/`, which is gitignored.

## 9. Testing

| Layer | Tooling | Runs on |
|---|---|---|
| Core (registry, schema, job resolution, naming, slug transliteration, scaffold, path safety) | pytest | CI (ubuntu + windows) |
| Validators | pytest with generated fixtures (below) | CI |
| Web API | pytest, in-process server; token/Host rejection tests | CI |
| JSX static | ESLint, `ecmaVersion: 3`, ExtendScript globals | CI |
| Figma plugin | `tsc --noEmit`, vitest on pure layout/naming modules | CI |
| Packaging smoke | Assemble the zip, extract it, run `runtime\python.exe -m studio_helper --selftest` | CI windows-latest |
| Adobe E2E | `pytest -m adobe` (skipped unless `STUDIO_HELPER_ADOBE=1`) | Owner's Windows machine with Illustrator/Photoshop |

**Fixtures.** `tests/fixtures/make_fixtures.py` generates them, using reportlab (a dev-only dependency) and pypdf to set boxes and OutputIntents:
- `good_a5.pdf`
- `bleed_short_left_bottom.pdf` — the background stops at the trim on two edges
- `rgb_image.pdf`
- `lowres_150ppi.pdf`
- `font_not_embedded.pdf`
- `no_bleedbox.pdf`
- `no_pdfx.pdf`
- Matching TIFF and PNG good/bad cases

**Real samples.** If `tests/fixtures/real/` exists, run validators on every file in it and compare against `expected.yaml` in the same folder. The first real sample must be a previously rejected print file.

**`--selftest`.** Imports all deps, validates the default registry, runs the validators on bundled mini-fixtures, starts the server on a random port and hits `/api/health`, then exits 0. This proves "runs with no install".

**Adobe E2E scenarios.**
1. Fixture job → `new_print_doc` → `inspect` → assert artboards, bleed, and CMYK.
2. Draw a full-bleed rectangle on `Background` → `preflight_export` → validate the PDF → all pass.
3. Shrink the rectangle to the trim → preflight fails on the right edges.
4. Panels job → artboards spaced by `panel_gap_mm`.
5. Photoshop: `new_digital_doc` → `export_digital` → PNG dimensions exact.

## 10. CI/CD (GitHub Actions)

- **`ci.yml`** (push/PR): lint (ruff, ESLint), typecheck, pytest (ubuntu + windows), pip-audit, license check, Figma plugin build and test.
- **`release.yml`** (tag `v*`, windows-latest):
  1. Download the pinned embeddable Python and verify its SHA256.
  2. Edit `python312._pth`.
  3. `pip install --target runtime/lib --require-hashes`.
  4. Build the Figma plugin.
  5. Assemble the layout from §5.1.
  6. Zip it.
  7. Run the **smoke test on the extracted zip**.
  8. Generate the SBOM and `SHA256SUMS`.
  9. Create the GitHub Release.
- The repo is private and she is added as a collaborator (the default assumption), or the owner downloads the zip for her.

## 11. Repo layout

```
app/studio_helper/{__main__.py, server.py, api/, core/, adobe/, validators/, poller.py, report/, web/, schema/}
adobe/{illustrator,photoshop,presets}/
figma-plugin/src/
defaults/registry.yaml
tests/{unit,validators,api,adobe,fixtures}/
packaging/{build_release.ps1, python.pth.template}
.github/workflows/{ci.yml, release.yml}
SPEC.md  README.md  README.txt(template)  requirements.in  requirements.lock  requirements-dev.lock
```

## 12. Milestones and acceptance criteria

**M0 — Skeleton and packaging** (de-risks the no-install requirement first).
- The release workflow produces a zip.
- On a clean Windows user account with no Python installed: extract, double-click, and the browser opens a "Hello" page.
- `--selftest` passes in CI on the extracted zip.
- Single-instance behavior works.

**M1 — Registry and New Job.**
- The default registry has placeholder formats marked TBD, and the schema validates it.
- New Job creates the folder tree and `job.json` with correct names, including Cyrillic transliteration.
- The Home, New Job, Job, and Registry screens work.
- Start revision bumps the version.

**M2 — Validators, poller, and report** (usable in "shadow mode" on files she exports manually).
- All fixture expectations pass.
- Dropping a file into `04_export/` updates the UI within about 5 s.
- `report.html` is generated.
- Real samples in `tests/fixtures/real/` are evaluated if present.

**M3 — Illustrator print generator.**
- The Setup check detects Illustrator and the preset.
- "Create Illustrator print file" produces a correct document: E2E scenarios 1 and 4 pass.
- The manual fallback works from File › Scripts.

**M4 — Illustrator preflight and export.**
- E2E scenarios 2 and 3 pass.
- TIFF auto-switch works, and the bleed is included in the TIFF.
- The source `.ai` is unchanged after export.
- Exported files appear as ✓ in the deliverables matrix.

**M5 — Digital: Photoshop and Figma.**
- E2E scenario 5 passes.
- The Figma plugin creates correctly named frames from `job.json`.
- Native Figma export into `04_export/` shows ✓ in the matrix.
- Zip auto-extract works.

## 13. Open items (owner fills these in; implementer uses placeholders until then)

- [ ] Print department spec: bleed (mm), safe zone, trim/crop marks yes/no, color profile / OutputIntent, exact PDF/X-1a settings (to build the `.joboptions`), TIFF threshold and TIFF ppi, vinyl requirements
- [ ] Full list of LED screens (id, name, px size, PNG/MP4, fps if video)
- [ ] 9 web banner sizes, any file size limits
- [ ] IG sizes used (e.g. 1080×1350 post, 1080×1920 story; confirm)
- [ ] Elevator sticker panel sizes and door gap, per location
- [ ] A previously rejected print file (for `tests/fixtures/real/`)
- [ ] Standard job types she wants in the dropdown

## 14. Implementer notes

- Work one milestone per PR. Keep the spec updated if a decision changes, and log it in a "Decisions" section at the end of this file.
- Keep ExtendScript thin, ES3-only, and fully wrapped in `try/finally` restoring app state. Always return the JSON envelope, even on exceptions.
- Illustrator coordinates are in points, and `artboardRect` is `[left, top, right, bottom]` with the y-axis up (top > bottom).
- Illustrator bleed is per document. Photoshop artboards need Action Manager code. Figma plugins cannot touch the disk or create files.
- When unsure about an Adobe API behavior, write a tiny probe script under `tests/adobe/probes/` and note the finding instead of guessing.
- Don't add dependencies without checking the license (§2.4) and that a win_amd64 wheel exists for the pinned Python.

## 15. Decisions

Decisions made during implementation that refine or resolve ambiguity in the spec above, in chronological order.

- 2026-09-22 — Repo created as `studio-helper` (private) under the `plpetkov-tech` GitHub account, built by Claude Code per this spec. Building milestone by milestone, PR per milestone, starting with M0.
- 2026-09-22 — M1 (registry + New Job): registry.yaml validates against a JSON Schema (draft-07, `additionalProperties: false` everywhere); errors are turned into file+line messages by composing the YAML into a Node tree and walking the same path jsonschema's error reports, so a mistake in registry.yaml points at the exact line without a second "YAML with line numbers" dependency.
- 2026-09-22 — New Job always submits an explicit `format_ids` list, never just a `job_type` name -- the job type is a client-side convenience that pre-ticks the checklist, but the final set she actually created (after any adds/removes) is what gets sent and embedded in job.json.
- 2026-09-22 — Two jobs created with the same name on the same day get an auto-suffixed slug/id (`-2`, `-3`, ...) instead of an error, since that's a plausible thing for her to do and shouldn't block her.
- 2026-09-22 — M1's deliverables "found/missing" status is a plain filename-stem match against `04_export/`, not real validation -- that's M2 (validators + poller). It's enough for the Home/Job progress display in the meantime and the shape (a list of `{..., status}`) won't need to change when M2 lands, just get richer.
- 2026-09-22 — The Job page's Print/Digital action buttons are visible now but disabled with a tooltip naming the milestone that implements them (M3-M5), rather than hidden, so the page's shape is already what it will be.
- 2026-09-22 — Frontend is a plain multi-page app (separate `.html` files per screen + a shared `static/api.js` token/fetch bootstrap), not a SPA -- no bundler ships in the runtime, and this keeps every page servable as a static file with zero build step.
- 2026-09-23 — M2 (validators, poller, report): "jobs opened in the last 14 days" (SPEC.md §6.7 poller) is implemented as "jobs *created* in the last 14 days" -- reusing job.json's existing `created` field rather than adding an "opened" timestamp to config.json. Simpler, and matches what the Home page already treats as "recent."
- 2026-09-23 — The PDF bleed-coverage check computes the overall ring fraction (SPEC.md's literal "more than 0.1% of pixels" rule) as `alpha-below-threshold(bleed crop) - alpha-below-threshold(trim crop)`, rather than a masked/L-shaped region -- two rectangular histogram reads instead of pixel-by-pixel masking. The four-edge breakdown used only for the *message* (which edges to name) uses corner-excluded strips, so one genuinely bad edge can't make an adjacent good edge falsely fail too (a real bug caught by the first fixture run: a corner overlap between a bad "left" edge and the thin "top" strip pushed "top" over the 0.1% threshold on its own).
- 2026-09-23 — pypdf's `.trimbox`/`.bleedbox` convenience properties silently fall back to the MediaBox when the underlying key is absent (per PDF inheritance rules), which would hide a genuinely missing box from the validator. The checks use `"/TrimBox" in page` / `"/BleedBox" in page` for presence, and only then build a `RectangleObject` from the raw value.
- 2026-09-23 — Test fixtures for the PDF validator are generated at test time (`tests/fixtures/make_fixtures.py`, session-scoped pytest fixture), not committed as binaries. reportlab (dev-only) always emits an unused default Helvetica font resource on every page regardless of whether it's drawn with -- stripped by the fixture generator's `_finalize()` step unless a fixture wants it kept (`font_not_embedded.pdf`), otherwise every generated fixture would spuriously fail the embedded-fonts check.
- 2026-09-23 — `--selftest` builds its own tiny PDF/PNG fixtures at runtime using only pypdf + Pillow (both shipped) to exercise the validators, rather than shipping binary fixtures or depending on reportlab (dev-only, never in the runtime).
- 2026-09-23 — M3 (Illustrator print generator), built without a Windows/Illustrator machine to verify against: `new_print_doc.jsx` and `inspect.jsx` are written to the documented Illustrator scripting API, but the actual document/artboard creation call (`app.documents.addDocument(colorSpace, preset)`) is the one piece **unverified against real Illustrator**. Flagged prominently in the file's own header comment, with an isolated probe script (`tests/adobe/probes/probe_document_preset.jsx`) for whoever runs this on a real machine first, per SPEC.md §14's own guidance for exactly this situation. Do not trust this file's document-creation step until that probe (or the real E2E scenarios) has run once for real.
- 2026-09-23 — Did not fabricate `adobe/presets/StudioHelper_X1a.joboptions`. It's a proprietary Adobe format (PDF/X-1a distiller parameters) that the print department's exact settings (§13 open item) should drive -- a wrong guess here is worse than an honest gap, since it's the one file directly responsible for print rejections. The Setup check's "PDF preset" item correctly reports "not found" until this file exists and Illustrator has it installed; nothing before then silently assumes it works.
- 2026-09-23 — `new_print_doc.jsx`'s pure geometry/grouping logic (bleed grouping, panel layout math, the canvas-size guard, naming) is executed for real in `tests/adobe/check_jsx_logic.js` via Node's `vm` module (stripping the ExtendScript `#include` lines first) -- not just reviewed. It's the one part of the file that doesn't touch Illustrator's DOM, so it's also the one part fully verifiable without a real copy of Illustrator; running it caught nothing this time, but it's now a permanent regression check in CI.
- 2026-09-23 — ESLint 9 uses flat config (`adobe/eslint.config.js`) rather than the legacy `.eslintrc.json` originally sketched in M0's `ci.yml`, since ESLint 9 dropped automatic eslintrc support. A custom processor strips `#include` lines before parsing (`#include` isn't valid JavaScript) while preserving line numbers for accurate error locations. Verified locally that `ecmaVersion: 3` actually rejects ES6+ syntax (arrow functions), not just that the config loads.
- 2026-09-23 — Long Adobe actions (Illustrator can take up to 120s to cold-start) now go through a real task-polling mechanism (`app/studio_helper/api/tasks.py`, `POST` an action → `task_id` → `GET /api/tasks/<id>`), per SPEC.md §6.2 rather than blocking the HTTP request. The Setup check also runs through this, since its Illustrator/preset check has the same latency profile.
- 2026-09-23 — Found and fixed a real hang while testing for real, not just reviewing: `xdg-open`/`explorer.exe`/`open` calls (used for every "open in file manager" action) had no timeout, and `xdg-open` genuinely hung in this sandbox's headless environment, timing out an HTTP request. All OS-opener calls (`app/studio_helper/api/openers.py`) now pass a 5s timeout and catch `subprocess.TimeoutExpired` alongside `OSError`.
- 2026-09-23 — M4 (Illustrator preflight and export), same unverified-against-real-Illustrator caveat as M3: `preflight_export.jsx` implements every check and both export gotchas from SPEC.md §6.4 (TIFF-before-PDF ordering since `saveAs` changes the open document's identity; temporarily expanding the artboard rect for TIFF export, since it clips to the artboard and drops the bleed). The bleed-coverage heuristic's interval-merging/gap-finding math (`maxGapMm`) has zero Illustrator dependency, so it's split out and executed for real in `tests/adobe/check_preflight_logic.js` (16 checks, including out-of-order and overlapping-interval edge cases) -- the `visibleBounds`-reading glue around it is not verifiable without a real copy of Illustrator.
- 2026-09-23 — A job can have more than one `.ai` file (one per distinct bleed value, per M3's grouping). "Check print file" and "Check & export print" both run over every file recorded in `job.json`'s `files.print`, returning one result per file; the Job page renders each as its own card, with "Export anyway" scoped to that specific file's path (not a global retry) when its preflight found a `fail` and the first export attempt was skipped.
- 2026-09-23 — Export doesn't write anything to job.json. The exported PDF/TIFF files land in `04_export/print/`, and the poller already watching that folder (SPEC.md M2) picks them up and validates them within its normal ~4-5s cadence -- verified end-to-end with a real background poller thread in this session, same as M2's own verification.
- 2026-09-23 — M5 (Photoshop + Figma), same placeholder-values basis as M3/M4. Photoshop's `makeArtboard()` (Action Manager descriptor for creating a real Photoshop Artboard) is the single highest-risk piece of code in the whole project -- higher than anything in the Illustrator scripts, because Photoshop's scripting DOM has no documented "create an artboard" method at all, and SPEC.md §6.5 itself says to capture the real descriptor with ScriptListener rather than write it from documentation. It's a best-effort reconstruction of a commonly-shared community pattern, explicitly flagged as such in the file header, with `tests/adobe/probes/probe_make_artboard.jsx` as the first thing to run on a real machine (including instructions for recording the real descriptor if it's wrong).
- 2026-09-23 — `export_digital.jsx` takes `export_dirs` (a kind → directory map), not a single `export_root`: different digital formats in the same PSD can have different kinds (screen/web/social), each mapping to its own `04_export/<kind-dir>` (SPEC.md §6.1). Python resolves that mapping; the JSX only does a plain dict lookup, keeping the naming decision out of the "thin JSX" layer (SPEC.md §4).
- 2026-09-23 — The Figma plugin is fully verified, unlike the Adobe side: real `npm ci` install, `tsc --noEmit`, `vitest run` (14 tests against `layout.ts`'s pure grid-layout/naming/frame-spec logic), and `esbuild` bundling all actually run and pass in this session, not just reviewed. Figma's plugin API is modern, typed, and stable, which is why this piece carries much higher confidence than the ExtendScript side.
- 2026-09-23 — Found and fixed a real toolchain incompatibility while verifying for real: `vitest@5.0.1` requires Node ≥22.12, but `ci.yml`'s `figma-plugin` job pinned Node 20 (fine for the Illustrator/Photoshop-only jobs, copied without checking for this one). Bumped that job's `node-version` to `24`.
- 2026-09-23 — The poller now auto-extracts `*.zip` files dropped into `04_export/` (SPEC.md §6.6, for the Figma plugin's secondary "Export all" path), using the same 2-scan file-stability rule as any other export. Only an entry's basename is ever used as the destination filename (never a path from inside the zip), guarding against zip-slip; entries not matching one of the job's `expected_stem`s are skipped, and the zip is deleted only after a successful extraction.
- 2026-09-23 — `v0.1.0` was tagged right after M0, then M1-M5 landed on `main` with no new tag -- the owner downloading and running "the release" was actually still running M0's placeholder "it's running" page with a Quit button and nothing else. Cut `v0.2.0` to fix that. From here on, tag a new release at the end of each milestone, not just M0, so "download the release" always means "download what was just built."
- 2026-09-23 — `v0.2.0`'s own build then surfaced a real packaging bug the smoke test doesn't catch (it only proves the *Python* app runs, not that the Figma plugin is importable): `build_release.ps1` flattened `figma-plugin/dist/*` straight into `figma-plugin/`, and never copied `ui.html` at all -- so the shipped plugin was missing its UI file entirely, and `code.js` sat one level up from where `manifest.json`'s `"main": "dist/code.js"` expects it. Found by actually downloading and inspecting the built zip, not just trusting a green CI run. Fixed in `v0.2.1`; `ui.html` is now copied explicitly and `dist/` stays a subfolder.
- 2026-09-23 — First real signal from an actual Windows machine with Illustrator/Photoshop installed: every Adobe action failed with `Could not start Illustrator.Application: [WinError -2147221008] CoInitialize has not been called`. This is the exact bug M3's own decisions entry flagged as the highest-risk unverified piece -- except it wasn't the documented-API-guess part (`app.documents.addDocument`) that broke, it was `bridge.py`'s own threading, which had no probe script because I didn't think to write one for it. Root cause: COM apartments are per-thread, and `AppContext.tasks` (SPEC.md §6.2) runs every action on a fresh background thread that never called `CoInitialize`. Compounding it, `connect()`'s original design spawned a *second* helper thread just to put a timeout around `CreateObject`, then handed the resulting COM object back to the caller's thread -- an apartment violation independent of the missing CoInitialize, since a COM object can't safely be used from a thread other than the one that created it. Fixed in `bridge.py`: `_ensure_com_initialized()` (thread-local, called once per thread before any COM call) and `connect()` now does everything synchronously on the calling thread, dropping the redundant inner timeout thread entirely -- the outer Task thread (SPEC.md §6.2) already keeps the UI unblocked, so a second timeout layer was never needed and was actively the source of the apartment bug. New regression tests assert the COM object is created and used on the same thread, and that `_ensure_com_initialized` runs before any client call.
- 2026-09-24 — After the CoInitialize fix: **`new_print_doc.jsx` now confirmed working on real Illustrator** -- "Created 1 print document," the M3 decisions entry's flagged risk (`app.documents.addDocument(colorSpace, preset)`) did not materialize. **Photoshop's `makeArtboard()` also confirmed working** -- the single highest-risk piece of code in the whole project (SPEC.md's M5 decisions entry), a from-memory reconstruction of an undocumented Action Manager descriptor, and it worked on the first real try: a document with the right artboards and the right name was created. The remaining Photoshop failure is isolated to the last line of `new_digital_doc.jsx`, `doc.saveAs(...)`: `"General Photoshop error occurred ... The parameters for command 'Save' are not currently valid."` Given genuine uncertainty about the exact cause (not the same category of "guessed API shape" risk as `makeArtboard` -- this is `PhotoshopSaveOptions` behaving unexpectedly after several `executeAction` calls), rather than guess again blindly, `saveDigitalDoc()` now (a) saves via `app.activeDocument` instead of the possibly-stale `doc` reference the earlier `executeAction` calls may have invalidated, (b) sets `PhotoshopSaveOptions` properties explicitly (`layers`, `embedColorProfile`, `alphaChannels`, `annotations`, `spotColors`) rather than relying on undocumented defaults, and (c) on failure, throws a diagnostic dump (resolved path, parent-folder existence, layer count, whether `app.activeDocument` and `doc` are even the same reference) instead of Photoshop's generic message -- so if this fix is wrong, the next real-machine test produces an exact cause instead of another round of the same guess.
- 2026-09-24 — Visual redesign of the local web UI (`app.css` + header markup across all 5 pages), since she's a working designer and the tool's own visual quality is not a neutral factor for her the way it might be for someone else. New design tokens (indigo accent, refined ink/gray scale, consistent spacing/radius/shadow scale), a small inline-CSS logo mark (no external asset, keeping the offline/no-CDN constraint from SPEC.md §2.3/§6.2), custom-styled checkboxes/select, and richer status badges/banners/code styling. No JS logic touched, no server-side changes, no new dependencies. Verified by actually rendering every page with headless Chromium (available in this sandbox) against the real running server with seeded jobs, not just reading the CSS -- caught one real, unrelated bug this way too: the Setup check page's Figma card still said "ships in a later update (milestone M5)," which was stale now that M5 had actually shipped; fixed the copy while in there.
- 2026-09-24 — Self-updater, requested directly ("can u make a new version with an auto updater... just dwl from raw gh... it could bee a button"): a "Check for updates" / "Download & install" button on the Home page. This deliberately bends the "fully offline, no network egress" hard constraint (§2.3 point 3, §8) -- amended both to a narrower, explicit invariant: no automatic or background network calls, ever; the *only* egress in the whole app is `studio_helper.updater`, and only from a direct button click, using stdlib `urllib` against GitHub's public release API and CDN (no `git` binary dependency, matching what was asked). `test_no_network.py` now asserts both halves: `--selftest` never leaves loopback (pre-existing) and never calls the updater either (new). The downloaded zip is verified against the release's own `SHA256SUMS` asset before anything is extracted -- refusing on any mismatch -- the same hash-pinning discipline `build_release.ps1` already applies to the embeddable Python download. Extraction reuses the poller's zip-slip guard (reject any entry resolving outside the destination). Because the running `pythonw.exe` and its DLLs can't be overwritten in place on Windows, the new version is staged into a *sibling* `StudioHelper-v<new>` folder next to the current install, then a small PowerShell helper (launched detached, `-ExecutionPolicy Bypass` for just that one process so it runs regardless of the machine's persistent policy) waits for this process's PID to actually exit, deletes the old folder, and starts the new one's `Start Studio Helper.bat` -- triggered by reusing the existing `/api/quit` shutdown path rather than inventing a second one. Also fixed a real latent bug found while wiring this up: `__version__` in `app/studio_helper/__init__.py` had been hand-set to `"0.1.0"` and never actually bumped through `v0.2.0`-`v0.2.4` -- `/api/health` had been reporting the wrong version in every release so far, silently, because nothing ever compared it to anything. `build_release.ps1` now stamps the real `__version__` from the git tag (`$Version`, already derived in `release.yml`) into the staged copy at build time and fails the build if the stamp doesn't take, so this can't drift again. Genuinely unverified: the PowerShell relaunch script and the embeddable Python's TLS support for the HTTPS GitHub calls, both because there's no Windows machine here to run them on -- same category of risk as the Adobe COM code, flagged the same way rather than guessed silently. Everything mockable (version comparison, SHA256 verification, zip-slip rejection, endpoint wiring, the offline invariant) has real tests, not just review.
- 2026-09-24 — Self-updater follow-up, from talking through what I'd still improve about it: the relaunch script deleted the old install outright once the new one started, with no check that the new one actually came up okay -- so a bad release (and packaging/COM-threading history says that's not hypothetical) would leave her with nothing to fall back to except manually re-downloading from GitHub. Changed `_RELAUNCH_PS1` to rename the old install to `<OldDir>.previous` instead of deleting it, only ever removing a stale `.previous` left over from the update before last, right before the current one takes its place -- so at most one rollback copy exists on disk at a time, and a broken update is recoverable by hand (delete the broken folder, drop `.previous` off the name, run its `Start Studio Helper.bat`) without needing the internet again. No live health check of the new process was added -- doing that reliably from a detached PowerShell script against a `pythonw.exe` that writes its own port/token to `instance.json` asynchronously felt like more moving parts than the actual risk justified; the rename-not-delete change covers the real failure mode (a release that doesn't start) far more simply. Verified with a content-based test asserting the script renames rather than deletes the current install (still can't execute real PowerShell here).
- 2026-09-26 — First real registry (malls) hit three problems on her machine. (1) Photoshop read the pixel sizes in her ruler units (cm): a 1080×1350px job became a ~122,000px-wide document, which is also why saveAs failed with "parameters for command 'Save' are not currently valid" (over .psd's 30,000px limit). This was probably the real cause of the 2026-09-23 save failure too. `SH.run` in `adobe/photoshop/lib/common.jsx` now forces pixel ruler/type units and restores them afterwards, and `new_digital_doc.jsx` refuses a layout over 30,000px with a plain message. (2) Editing `scale` in the registry had no effect on an existing job, because job.json snapshots formats by design. Oversize print formats are now auto-scaled to 1:10 at job creation and when creating the Illustrator file. (3) A full mall-print job (~53 m²) can't fit Illustrator's 33 m² canvas at all, so artboards are now packed into rows and split across files, each sheet centred on the new document's initial artboard (taken as the canvas centre). Artboards are added with `doc.artboards.add()` instead of `numArtboards`. That call is unverified on a real machine; the packing/centring math is covered in `tests/adobe/check_jsx_logic.js`, including against the real mall-print formats.
