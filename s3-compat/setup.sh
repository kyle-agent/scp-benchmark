#!/usr/bin/env bash
# Bootstrap ceph/s3-tests into a local venv for S3 compatibility testing.
# Idempotent: safe to re-run. Needs network access to GitHub and PyPI.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
S3TESTS_DIR="$SCRIPT_DIR/s3-tests"
VENV_DIR="$SCRIPT_DIR/.venv"
S3TESTS_REPO="https://github.com/ceph/s3-tests"
# Pinned for reproducible runs; bump deliberately.
S3TESTS_PIN="ff80f9e43e3bab000f5cd3685ee0d3bf601eb44c"

if [ ! -d "$S3TESTS_DIR/.git" ]; then
  echo "[setup] cloning ceph/s3-tests ..."
  git clone "$S3TESTS_REPO" "$S3TESTS_DIR"
fi
echo "[setup] checking out pinned commit $S3TESTS_PIN ..."
git -C "$S3TESTS_DIR" checkout -q "$S3TESTS_PIN" 2>/dev/null \
  || { git -C "$S3TESTS_DIR" fetch origin && git -C "$S3TESTS_DIR" checkout -q "$S3TESTS_PIN"; }

if [ ! -d "$VENV_DIR" ]; then
  echo "[setup] creating venv ..."
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip >/dev/null
echo "[setup] installing s3-tests requirements ..."
python -m pip install -r "$S3TESTS_DIR/requirements.txt"

echo "[setup] done."
echo "        venv:     $VENV_DIR"
echo "        s3-tests: $S3TESTS_DIR ($S3TESTS_PIN)"
echo "        next:     cp .env.example .env  # fill in creds, then ./run.sh"
