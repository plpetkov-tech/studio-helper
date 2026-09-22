#!/usr/bin/env bash
# Regenerates requirements.lock with SHA256 hashes for the exact
# win_amd64 / CPython 3.12 wheels used by the shipped runtime
# (SPEC.md §5.1, §8). Can be run from Linux or Windows dev machines --
# it only downloads wheels, it never builds them.
#
# Usage: packaging/lock_requirements.sh
set -euo pipefail

cd "$(dirname "$0")/.."
work="$(mktemp -d)"
venv="$work/venv"
wheels="$work/wheels"

python3 -m venv "$venv"
"$venv/bin/pip" install --upgrade pip >/dev/null
mkdir -p "$wheels"

"$venv/bin/pip" download \
    --platform win_amd64 --python-version 312 --implementation cp --abi cp312 \
    --only-binary=:all: -d "$wheels" \
    -r requirements.in

{
  echo "# Generated for: Python 3.12 (CPython), platform win_amd64"
  echo "# Regenerate with packaging/lock_requirements.sh. Do not hand-edit hashes."
  echo
  for whl in "$wheels"/*.whl; do
    name_ver="$(basename "$whl" .whl)"
    hash="$(sha256sum "$whl" | cut -d' ' -f1)"
    echo "# $name_ver -> sha256:$hash"
  done
}

echo
echo "Wheels and hashes listed above. Merge the ones that changed into" \
     "requirements.lock by hand, in the pip --require-hashes format:"
echo '  package==X.Y.Z \'
echo '      --hash=sha256:...'
echo
echo "Wheel cache kept at: $wheels"
