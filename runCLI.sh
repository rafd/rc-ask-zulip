#!/usr/bin/env bash

# Start FastAPI on :8000 (background), wait for /api/checkin-pair, then run the
# Rc-Checkins-TUI CLI (Ink). Does not start Ollama — only the check-in API is needed.
# For the CLI, use DEV_AUTH_BYPASS=1 in .env (plain fetch has no session cookie).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TUI_DIR="$SCRIPT_DIR/Rc-Checkins-TUI/rcAskZulip"
API_URL="http://127.0.0.1:8000/api/checkin-pair"
UVICORN_PID=""

cleanup() {
  if [[ -n "$UVICORN_PID" ]] && kill -0 "$UVICORN_PID" 2>/dev/null; then
    kill "$UVICORN_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
echo "🚀 Checking for dependencies and setting up virtual environment"
#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
  echo "📦 No .venv found; running ./install.sh"
  "$SCRIPT_DIR/install.sh"
fi
uv sync
echo "✅ Virtual environment setup complete"

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
echo "🚀 Loading environment variables"
#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
if [[ -f .env ]]; then
  echo "🔑 Loading .env"
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

if [[ ! -d "$TUI_DIR" ]]; then
  echo "❌ Missing $TUI_DIR — init the submodule: git submodule update --init --recursive"
  exit 1
fi

LOG_LEVEL_LOWER="$(echo "${LOG_LEVEL:-INFO}" | tr '[:upper:]' '[:lower:]')"
case "$LOG_LEVEL_LOWER" in
  debug | info | warning | error | critical) ;;
  *) LOG_LEVEL_LOWER="info" ;;
esac

port_has_listener() {
  bash -c "echo >/dev/tcp/127.0.0.1/8000" 2>/dev/null
}

api_ready() {
  curl -sf "$API_URL" &>/dev/null
}

if api_ready; then
  echo "✅ API already responding at $API_URL — not starting another server"
elif port_has_listener; then
  echo "❌ Port 8000 is in use but $API_URL did not succeed."
  echo "   Stop the other process, or start this project's API so check-in data is available."
  echo "   (For the CLI you need DEV_AUTH_BYPASS=1 in .env unless you add session cookies.)"
  exit 1
else
  echo "🔌 Starting API — http://127.0.0.1:8000/"
  "$SCRIPT_DIR/.venv/bin/python" -m uvicorn main:app \
    --host 127.0.0.1 --port 8000 --log-level "$LOG_LEVEL_LOWER" &
  UVICORN_PID=$!
fi

echo "⏳ Waiting for $API_URL …"
ready=0
for _ in $(seq 1 60); do
  if api_ready; then
    ready=1
    break
  fi
  sleep 0.5
done
if [[ "$ready" -ne 1 ]]; then
  echo "❌ API did not become ready in time."
  echo "   Ensure ZULIP_* is set in .env and DEV_AUTH_BYPASS=1 for unauthenticated CLI access."
  exit 1
fi
echo "✅ API ready"

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
echo "🖥️  Building check-in TUI (Node) if needed"
#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
cd "$TUI_DIR"
if [[ ! -f dist/cli.js ]]; then
  if [[ ! -x "$(command -v npm)" ]]; then
    echo "❌ npm not found — install Node.js ≥ 22 and npm"
    exit 1
  fi
  npm ci
  npm run build
fi

echo "🖥️  Starting TUI (Ctrl+C quits; API stops if this script started it)"
node dist/cli.js
