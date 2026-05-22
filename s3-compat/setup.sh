#!/usr/bin/env bash
# Set up the S3-compatibility test harness: a virtualenv plus the ceph/s3-tests
# suite vendored locally. Safe to re-run; it only does the missing steps.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

S3TESTS_REPO="${S3TESTS_REPO:-https://github.com/ceph/s3-tests}"
S3TESTS_REF="${S3TESTS_REF:-master}"
PY="$ROOT/.venv/bin/python"

echo "[1/3] Creating virtualenv (.venv) ..."
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
"$PY" -m pip install --quiet --upgrade pip

echo "[2/3] Fetching ceph/s3-tests (ref: ${S3TESTS_REF}) ..."
if [ ! -d vendor/s3-tests/.git ]; then
  mkdir -p vendor
  git clone "$S3TESTS_REPO" vendor/s3-tests
fi
git -C vendor/s3-tests fetch --quiet origin
git -C vendor/s3-tests checkout --quiet "$S3TESTS_REF"

echo "[3/3] Installing s3-tests dependencies ..."
"$PY" -m pip install --quiet -r vendor/s3-tests/requirements.txt

echo
echo "Setup complete. Next:"
echo "  1) cp .env.example .env    # then fill in your SCP object storage credentials"
echo "  2) ./run.sh                # results land in results/report.md"
