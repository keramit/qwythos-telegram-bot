#!/bin/bash
# ==========================================================================
# QWYTHOS Telegram Bot — local launcher (macOS)
# ==========================================================================
# Runs the bot in LONG-POLLING mode on this Mac, under caffeinate so the
# machine does not idle-sleep while the bot is polling Telegram.
#
# Secrets are NOT stored here. They are read from, in order:
#   1. an existing environment variable
#   2. the .env file next to this script
#   3. ~/.dsh/.credentials.yaml  (refs.TELEGRAM_BOT_TOKEN / refs.GROQ_API_KEY)
# ==========================================================================
set -euo pipefail

cd "$(dirname "$0")"

VENV="${VENV:-/Users/ahmedabushama/venv}"
CREDENTIALS="${CREDENTIALS:-$HOME/.dsh/.credentials.yaml}"

# --- load .env if present (does not override real env vars) ---------------
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# --- fall back to the DSH credentials file --------------------------------
if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${GROQ_API_KEY:-}" ]]; then
    if [[ -f "$CREDENTIALS" ]]; then
        eval "$("$VENV/bin/python" - "$CREDENTIALS" <<'PY'
import sys, yaml, shlex
refs = (yaml.safe_load(open(sys.argv[1])) or {}).get("refs", {})
for key in ("TELEGRAM_BOT_TOKEN", "GROQ_API_KEY"):
    if refs.get(key):
        print(f"export {key}={shlex.quote(str(refs[key]))}")
PY
)"
    fi
fi

# --- validate -------------------------------------------------------------
if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    echo "TELEGRAM_BOT_TOKEN is not set (env / .env / $CREDENTIALS)" >&2
    exit 1
fi
if [[ -z "${GROQ_API_KEY:-}" ]]; then
    echo "GROQ_API_KEY is not set (env / .env / $CREDENTIALS)" >&2
    exit 1
fi
export TELEGRAM_BOT_TOKEN GROQ_API_KEY

# --- activate venv --------------------------------------------------------
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# --- run under caffeinate -------------------------------------------------
# -i prevents idle sleep on battery and AC; -s adds AC protection.
# NOTE: lid-close sleep is NOT defeated by caffeinate — use:
#       sudo pmset -a disablesleep 1
echo "Starting QWYTHOS (long-polling) with caffeinate"
exec /usr/bin/caffeinate -is "$VENV/bin/python" app.py
