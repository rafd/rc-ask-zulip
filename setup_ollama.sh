#!/usr/bin/env bash
# Install Ollama (optional: Homebrew) and pull the chat model used by this app.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

model="${OPENAI_MODEL:-llama3.1}"

usage() {
  cat <<'EOF'
Usage: ./setup_ollama.sh [options]

  Ensures the ollama CLI is available, then pulls OPENAI_MODEL (default: llama3.1).
  Loads .env from the repo root if present.

Options:
  --brew    Run `brew bundle` here first (macOS Homebrew: installs ollama from Brewfile)
  -h, --help

Environment:
  OPENAI_MODEL   Model name to pull (default: llama3.1)

After this, start the app with ./run.sh run (which can start ollama serve if needed).
EOF
}

with_brew=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --brew)
      with_brew=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$with_brew" -eq 1 ]]; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "error: --brew requires Homebrew (https://brew.sh/)" >&2
    exit 1
  fi
  if [[ ! -f "$ROOT/Brewfile" ]]; then
    echo "error: Brewfile not found in $ROOT" >&2
    exit 1
  fi
  brew bundle
fi

if ! command -v ollama >/dev/null 2>&1; then
  cat <<'EOF' >&2
error: ollama CLI not found.

  Install: https://ollama.com/download
  macOS with Homebrew (from this repo): ./setup_ollama.sh --brew
EOF
  exit 1
fi

echo "Pulling model: $model"
ollama pull "$model"

if curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
  echo "Ollama API is up at http://127.0.0.1:11434"
else
  echo "tip: start the server with: ollama serve  (or: open -a Ollama on macOS)" >&2
fi
