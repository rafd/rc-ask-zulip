#!/usr/bin/env bash
# Local dev entrypoint: install deps (uv) and run the FastAPI app.

# -e: exit on first failing command
# -u: error on unset variables
# -o pipefail: pipeline fails if any stage fails
set -euo pipefail

# Run from repo root so paths like static/ and db files resolve no matter where you invoke ./dev.sh from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage: ./dev.sh <command>

  setup   Install dependencies (uv sync)
  run     Start the API dev server with reload (default)

Requires uv: https://docs.astral.sh/uv/
Set ZULIP_SITE, ZULIP_EMAIL, ZULIP_API_KEY, and OPENAI_API_KEY in .env
EOF
}

# Default subcommand is "run" so ./dev.sh alone starts the server.
cmd="${1:-run}"

# Handle help before requiring uv so newcomers can read usage on a machine without uv yet.
case "$cmd" in
  help | -h | --help)
    usage
    exit 0
    ;;
esac

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is not installed. See https://docs.astral.sh/uv/" >&2
  exit 1
fi

case "$cmd" in
  setup)
    # Creates/updates .venv from uv.lock and pyproject.toml.
    uv sync
    ;;
  run)
    # main.py starts uvicorn with reload when executed as __main__.
    uv run python main.py
    ;;
  *)
    # Anything other than setup | run | help
    echo "error: unknown command: $cmd" >&2
    usage
    exit 1
    ;;
esac
