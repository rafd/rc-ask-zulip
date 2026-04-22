#!/usr/bin/env bash

# Run the FastAPI dev server (uses .venv next to this script).
# Runs ./Ollama.sh --ollama-only first unless --no-ollama.
# Runs ./install.sh if .venv is missing.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if the virtual environment exists, if not, run the install script - to setup dependencies
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
  echo "📦 No .venv found; running ./install.sh"
  "$SCRIPT_DIR/install.sh"
fi

# Check if the ollama is running, if not, run the ollama script - to start the ollama server
if [[ ! -f "$SCRIPT_DIR/.ollama-serve.log" ]]; then
  echo "🦙 No .ollama-serve.log found; running ./Ollama.sh --ollama-only"
  "$SCRIPT_DIR/Ollama.sh" --ollama-only
fi

# Loading the environment variables from the .env file
if [[ -f .env ]]; then
  echo "🔑 Loading .env"
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# Checking if the python executable is in the virtual environment
echo "🔌 Using virtual environment: $SCRIPT_DIR/.venv"
echo "🐍 Starting the app — http://127.0.0.1:8000/"
exec "$SCRIPT_DIR/.venv/bin/python" main.py
