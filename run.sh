#!/usr/bin/env bash

# Run the FastAPI dev server (uses .venv next to this script).
# After .env: curls ${OLLAMA_HOST}/api/tags; if Ollama is down, runs ./Ollama.sh --ollama-only.
# Runs ./install.sh if .venv is missing.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
echo "🚀 Checking for dependencies and setting up virtual environment"
#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
# Check if the virtual environment exists, if not, run the install script - to setup dependencies
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

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
echo "🚀 Checking if the ollama server is running"
#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
OLLAMA_HOST="${OLLAMA_HOST%/}"
if ! curl -sf "${OLLAMA_HOST}/api/tags" &>/dev/null; then
  echo "🦙 Ollama not responding at ${OLLAMA_HOST}; running ./Ollama.sh --ollama-only to start the ollama server"
  "$SCRIPT_DIR/Ollama.sh" --ollama-only
fi
echo "✅ Ollama server ready"

# Checking if the python executable is in the virtual environment
echo "🔌 Using virtual environment: $SCRIPT_DIR/.venv"
echo "🐍 Starting the app — http://127.0.0.1:8000/"
exec "$SCRIPT_DIR/.venv/bin/python" main.py
