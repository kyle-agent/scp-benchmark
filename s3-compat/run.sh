#!/usr/bin/env bash
# Run the ceph/s3-tests S3 suite against a target endpoint and build a report.
#
# Config comes from environment variables (see .env.example). Required:
#   S3_ENDPOINT, S3_MAIN_ACCESS_KEY, S3_MAIN_SECRET_KEY,
#   S3_ALT_ACCESS_KEY, S3_ALT_SECRET_KEY
# Optional: S3_REGION (default kr-west1), S3_ADDRESSING_STYLE (default path),
#   S3_BUCKET_PREFIX.
#
# Extra args are passed straight to pytest, e.g.:
#   ./run.sh s3tests/functional/test_s3.py -m 'not fails_on_aws'
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
S3TESTS_DIR="$SCRIPT_DIR/s3-tests"
VENV_DIR="$SCRIPT_DIR/.venv"
RESULTS_DIR="$SCRIPT_DIR/results"
CONF_FILE="$SCRIPT_DIR/s3tests.conf"

# Load secrets/config from .env if present (gitignored).
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

: "${S3_ENDPOINT:?set S3_ENDPOINT, e.g. https://object-store.kr-west1.e.samsungsdscloud.com}"
: "${S3_MAIN_ACCESS_KEY:?set S3_MAIN_ACCESS_KEY}"
: "${S3_MAIN_SECRET_KEY:?set S3_MAIN_SECRET_KEY}"
: "${S3_ALT_ACCESS_KEY:?set S3_ALT_ACCESS_KEY}"
: "${S3_ALT_SECRET_KEY:?set S3_ALT_SECRET_KEY}"
S3_REGION="${S3_REGION:-kr-west1}"
S3_ADDRESSING_STYLE="${S3_ADDRESSING_STYLE:-path}"
S3_BUCKET_PREFIX="${S3_BUCKET_PREFIX:-s3compat-{random}-}"

if [ ! -d "$VENV_DIR" ] || [ ! -d "$S3TESTS_DIR" ]; then
  echo "run.sh: missing venv or s3-tests; run ./setup.sh first" >&2
  exit 1
fi

# Decompose the endpoint URL into host / port / scheme for the conf [DEFAULT].
proto="${S3_ENDPOINT%%://*}"
hostport="${S3_ENDPOINT#*://}"; hostport="${hostport%%/*}"
host="${hostport%%:*}"
if [[ "$hostport" == *:* ]]; then
  port="${hostport##*:}"
elif [ "$proto" = "https" ]; then
  port=443
else
  port=80
fi
[ "$proto" = "https" ] && is_secure=True || is_secure=False

mkdir -p "$RESULTS_DIR"

# Render the live config (gitignored) from the template.
S3_HOST="$host" S3_PORT="$port" S3_IS_SECURE="$is_secure" \
S3_REGION="$S3_REGION" S3_BUCKET_PREFIX="$S3_BUCKET_PREFIX" \
S3_MAIN_ACCESS_KEY="$S3_MAIN_ACCESS_KEY" S3_MAIN_SECRET_KEY="$S3_MAIN_SECRET_KEY" \
S3_ALT_ACCESS_KEY="$S3_ALT_ACCESS_KEY" S3_ALT_SECRET_KEY="$S3_ALT_SECRET_KEY" \
python3 "$SCRIPT_DIR/render_conf.py" "$SCRIPT_DIR/s3tests.conf.template" "$CONF_FILE"

# Force addressing style + signing region via a scoped AWS config. Path-style
# avoids needing wildcard-DNS / wildcard-host allowlisting for virtual-hosted
# bucket subdomains, which most S3-compatible stores require anyway.
AWS_CFG="$RESULTS_DIR/aws_config.ini"
cat > "$AWS_CFG" <<EOF
[default]
region = $S3_REGION
s3 =
    addressing_style = $S3_ADDRESSING_STYLE
EOF
export AWS_CONFIG_FILE="$AWS_CFG"
export AWS_DEFAULT_REGION="$S3_REGION"

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if [ "$#" -gt 0 ]; then
  TARGET=("$@")
else
  TARGET=("s3tests/functional/test_s3.py")
fi
JUNIT="$RESULTS_DIR/results.xml"
LOG="$RESULTS_DIR/pytest.log"

echo "[run] endpoint:   $S3_ENDPOINT"
echo "[run] region:     $S3_REGION   addressing: $S3_ADDRESSING_STYLE"
echo "[run] target:     ${TARGET[*]}"

( cd "$S3TESTS_DIR" && S3TEST_CONF="$CONF_FILE" python -m pytest -v \
    --junitxml="$JUNIT" "${TARGET[@]}" ) 2>&1 | tee "$LOG"
status=${PIPESTATUS[0]}
echo "[run] pytest exit: $status"

if [ ! -f "$JUNIT" ]; then
  echo "[run] no junit produced (collection/setup failed) - see $LOG" >&2
  exit "${status:-1}"
fi

python3 "$SCRIPT_DIR/report.py" "$JUNIT" --out-dir "$RESULTS_DIR" --endpoint "$S3_ENDPOINT"
echo "[run] report: $RESULTS_DIR/report.md (json: $RESULTS_DIR/report.json)"
