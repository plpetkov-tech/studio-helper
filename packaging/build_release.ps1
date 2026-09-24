<#
.SYNOPSIS
  Assembles the Studio Helper release zip (SPEC.md §5.1, §10 release.yml).

.DESCRIPTION
  Run on windows-latest with a full CPython 3.12 on PATH (via
  actions/setup-python) -- that full Python does the `pip install
  --target`, it is never shipped. The embeddable Python downloaded
  here becomes runtime\python(w).exe in the zip.

.PARAMETER Version
  App version, e.g. "0.1.0". Used in the zip file name and SBOM.

.EXAMPLE
  pwsh packaging/build_release.ps1 -Version 0.1.0
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$DistDir = Join-Path $RepoRoot "dist"
$StageName = "StudioHelper-v$Version"
$StageDir = Join-Path $DistDir $StageName
$ZipPath = Join-Path $DistDir "$StageName.zip"

# Pinned embeddable Python (SPEC.md §8 supply chain: URL + SHA256 pin).
$PythonVersion = "3.12.7"
$PythonZipUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$PythonZipSha256 = "0d57bb6cb078b74d23dbfe91f77d6780d45bed328911609f1f7ee2ba1606bf44"

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

# --- clean stage -----------------------------------------------------

Write-Step "Cleaning $StageDir"
if (Test-Path $StageDir) { Remove-Item -Recurse -Force $StageDir }
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

# --- 1. download + verify embeddable Python ---------------------------

Write-Step "Downloading embeddable Python $PythonVersion"
$pyZip = Join-Path $DistDir "python-embed.zip"
Invoke-WebRequest -Uri $PythonZipUrl -OutFile $pyZip
$actualHash = (Get-FileHash -Path $pyZip -Algorithm SHA256).Hash.ToLower()
if ($actualHash -ne $PythonZipSha256) {
    throw "Embeddable Python SHA256 mismatch. Expected $PythonZipSha256, got $actualHash. Refusing to continue (SPEC.md §8)."
}
Write-Host "SHA256 verified: $actualHash"

$runtimeDir = Join-Path $StageDir "runtime"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
Expand-Archive -Path $pyZip -DestinationPath $runtimeDir -Force
Remove-Item $pyZip

# --- 2. edit python312._pth ---------------------------------------------

Write-Step "Writing runtime/python312._pth"
Copy-Item (Join-Path $PSScriptRoot "python312._pth.template") (Join-Path $runtimeDir "python312._pth") -Force

# --- 3. install locked runtime dependencies into runtime\lib -----------

Write-Step "Installing runtime dependencies (hash-locked)"
$libDir = Join-Path $runtimeDir "lib"
New-Item -ItemType Directory -Force -Path $libDir | Out-Null
python -m pip install `
    --target $libDir `
    --require-hashes `
    --no-deps `
    -r (Join-Path $RepoRoot "requirements.lock")
# --no-deps is safe here: requirements.lock already lists the full
# resolved transitive closure (SPEC.md §5.1), and --require-hashes
# already refuses anything not explicitly pinned.

# --- 4. Figma plugin (optional until milestone M5) ---------------------

$figmaSrc = Join-Path $RepoRoot "figma-plugin"
$figmaPkgJson = Join-Path $figmaSrc "package.json"
$figmaStage = Join-Path $StageDir "figma-plugin"
New-Item -ItemType Directory -Force -Path $figmaStage | Out-Null

if (Test-Path $figmaPkgJson) {
    Write-Step "Building Figma plugin"
    Push-Location $figmaSrc
    try {
        npm ci
        npm run build
    }
    finally {
        Pop-Location
    }
    # manifest.json's "main" is "dist/code.js" and "ui" is "ui.html",
    # both resolved relative to the manifest itself -- ui.html must be
    # copied explicitly (esbuild only builds code.js), and dist/ must
    # stay a subfolder, not get flattened into figma-plugin/.
    Copy-Item (Join-Path $figmaSrc "manifest.json") $figmaStage -Force
    Copy-Item (Join-Path $figmaSrc "ui.html") $figmaStage -Force
    New-Item -ItemType Directory -Force -Path (Join-Path $figmaStage "dist") | Out-Null
    Copy-Item (Join-Path $figmaSrc "dist" "*") (Join-Path $figmaStage "dist") -Recurse -Force
}
else {
    Write-Host "No figma-plugin/package.json yet (pre-M5) -- shipping manifest only if present."
    if (Test-Path (Join-Path $figmaSrc "manifest.json")) {
        Copy-Item (Join-Path $figmaSrc "manifest.json") $figmaStage -Force
    }
}

# --- 5. copy app payload ------------------------------------------------

Write-Step "Copying app / adobe / defaults / LICENSES"

function Copy-Clean($src, $dst) {
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force
    Get-ChildItem -Path $dst -Recurse -Directory -Filter '__pycache__' |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $dst -Recurse -File -Include '*.pyc', '.gitkeep' |
        Remove-Item -Force -ErrorAction SilentlyContinue
    # Dev-only lint tooling, not needed by the shipped app.
    Get-ChildItem -Path $dst -Recurse -File -Include 'eslint.config.js' |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

Copy-Clean (Join-Path $RepoRoot "app") (Join-Path $StageDir "app")
Copy-Clean (Join-Path $RepoRoot "adobe") (Join-Path $StageDir "adobe")
Copy-Clean (Join-Path $RepoRoot "defaults") (Join-Path $StageDir "defaults")

# The checked-in __version__ is a dev-time placeholder; the tag is the
# real source of truth for a release (release.yml derives $Version
# from it). Stamping it here, not by hand in the repo, is what keeps
# /api/health and the self-updater's "am I current" check honest --
# a hand-bumped constant had already drifted (stuck at 0.1.0 through
# v0.2.0-v0.2.4) before this existed (SPEC.md §15 decisions).
$initPath = Join-Path $StageDir "app\studio_helper\__init__.py"
$stamped = (Get-Content -Raw $initPath) -replace '__version__ = "[^"]*"', "__version__ = `"$Version`""
if ($stamped -notmatch [regex]::Escape("__version__ = `"$Version`"")) {
    throw "Failed to stamp version $Version into $initPath -- refusing to build."
}
Set-Content -Path $initPath -Value $stamped -NoNewline

if (Test-Path (Join-Path $RepoRoot "LICENSES")) {
    Copy-Clean (Join-Path $RepoRoot "LICENSES") (Join-Path $StageDir "LICENSES")
}

Copy-Item (Join-Path $PSScriptRoot "Start Studio Helper.bat") $StageDir -Force
Copy-Item (Join-Path $RepoRoot "README.txt.template") (Join-Path $StageDir "README.txt") -Force

# --- SBOM ----------------------------------------------------------------

Write-Step "Generating SBOM"
python (Join-Path $PSScriptRoot "generate_sbom.py") `
    (Join-Path $RepoRoot "requirements.lock") $Version `
    | Out-File -Encoding utf8 (Join-Path $StageDir "SBOM.cdx.json")
# Also drop a copy next to the zip, so it can be attached to the
# GitHub Release as its own downloadable asset (SPEC.md §10 step 8).
Copy-Item (Join-Path $StageDir "SBOM.cdx.json") (Join-Path $DistDir "SBOM.cdx.json") -Force

# --- 6. zip ---------------------------------------------------------------

Write-Step "Zipping $ZipPath"
if (Test-Path $ZipPath) { Remove-Item $ZipPath }
Compress-Archive -Path $StageDir -DestinationPath $ZipPath

# --- 7. smoke test: extract the ZIP and run --selftest --------------------

Write-Step "Smoke-testing the extracted zip"
$smokeDir = Join-Path $DistDir "smoke"
if (Test-Path $smokeDir) { Remove-Item -Recurse -Force $smokeDir }
Expand-Archive -Path $ZipPath -DestinationPath $smokeDir
$extractedRoot = Join-Path $smokeDir $StageName
$pythonExe = Join-Path $extractedRoot "runtime\python.exe"

& $pythonExe -m studio_helper --selftest
if ($LASTEXITCODE -ne 0) {
    throw "Selftest failed on the extracted zip (exit $LASTEXITCODE). See output above."
}
Remove-Item -Recurse -Force $smokeDir

# --- 8. checksums -----------------------------------------------------------

Write-Step "Writing SHA256SUMS"
$zipHash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLower()
"$zipHash  $StageName.zip" | Out-File -Encoding ascii (Join-Path $DistDir "SHA256SUMS")

Write-Step "Done"
Write-Host "Release artifact: $ZipPath"
Write-Host "SBOM:             $(Join-Path $StageDir 'SBOM.cdx.json')"
Write-Host "Checksums:        $(Join-Path $DistDir 'SHA256SUMS')"
