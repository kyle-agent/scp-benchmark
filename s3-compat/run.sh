#!/usr/bin/env bash
# Run the ceph/s3-tests suite against an S3-compatible endpoint described in
# .env, then render a compatibility matrix to results/report.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

[ -f .env ]            || { echo "ERROR: .env not found. Copy .env.example to .env and fill it in." >&2; exit 1; }
[ -d .venv ]          || { echo "ERROR: .venv not found. Run ./setup.sh first." >&2; exit 1; }
[ -d vendor/s3-tests ] || { echo "ERROR: vendor/s3-tests missing. Run ./setup.sh first." >&2; exit 1; }

set -a; . ./.env; set +a

: "${S3_ENDPOINT_URL:?Set S3_ENDPOINT_URL in .env}"
: "${S3_ACCESS_KEY:?Set S3_ACCESS_KEY in .env}"
: "${S3_SECRET_KEY:?Set S3_SECRET_KEY in .env}"

PY="$ROOT/.venv/bin/python"
mkdir -p results

CONF="$ROOT/results/s3tests.generated.conf"
AWSCFG="$ROOT/results/aws_config"
JUNIT="$ROOT/results/junit.xml"
REPORT="$ROOT/results/report.md"

# 1) Translate .env into an s3-tests INI config.
"$PY" lib/gen_config.py "$CONF"

# 2) Force the bucket addressing style (SCP usually needs path-style). boto3
#    clients in s3-tests don't set this, so it is supplied via the shared
#    AWS config file.
{
  echo "[default]"
  echo "s3 ="
  echo "    addressing_style = ${S3_ADDRESSING_STYLE:-path}"
} > "$AWSCFG"

export S3TEST_CONF="$CONF"
export AWS_CONFIG_FILE="$AWSCFG"
export AWS_DEFAULT_REGION="${S3_REGION:-us-east-1}"
export AWS_REGION="${S3_REGION:-us-east-1}"
export PYTHONPATH="$ROOT/lib${PYTHONPATH:+:$PYTHONPATH}"
# Keep retry backoff from dominating wall time (many compat tests expect the
# server to reject a request; retrying those just wastes round trips).
export AWS_MAX_ATTEMPTS="${AWS_MAX_ATTEMPTS:-2}"
export AWS_RETRY_MODE="${AWS_RETRY_MODE:-standard}"

PATHS="${S3_TEST_PATHS:-s3tests/functional/test_s3.py s3tests/functional/test_headers.py}"
MARKER_ARGS=()
[ -n "${S3_TEST_MARKERS:-}" ] && MARKER_ARGS=(-m "$S3_TEST_MARKERS")

echo
echo "Running s3-tests against ${S3_ENDPOINT_URL} (this can take a while) ..."
set +e
( cd vendor/s3-tests && "$PY" -m pytest \
    -p s3compat_plugin \
    --junitxml="$JUNIT" \
    --continue-on-collection-errors \
    -q -p no:cacheprovider \
    "${MARKER_ARGS[@]}" \
    ${S3_PYTEST_EXTRA:-} \
    $PATHS )
PYTEST_RC=$?
set -e

[ -f "$JUNIT" ] || { echo "ERROR: no JUnit results produced (pytest rc=$PYTEST_RC). See output above." >&2; exit 1; }

# 3) Render the compatibility matrix.
S3TESTS_REF="$(git -C vendor/s3-tests rev-parse --short HEAD 2>/dev/null || echo unknown)"
"$PY" lib/report.py "$JUNIT" "$REPORT" \
    --endpoint "$S3_ENDPOINT_URL" \
    --s3tests-ref "$S3TESTS_REF"

echo
echo "Report written to: $REPORT"
