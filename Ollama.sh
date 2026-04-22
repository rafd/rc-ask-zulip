#!/usr/bin/env bash

# Start Ollama (if needed) and optionally Open WebUI — http://127.0.0.1:8080 by default.
#   ./Ollama.sh              → ensure :11434, then Open WebUI (needs uv; run ./install.sh first)
#   ./Ollama.sh --ollama-only → ensure :11434 only, then exit (for ./run.sh)

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

OLLAMA_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ollama-only)
      OLLAMA_ONLY=1
      shift
      ;;
    -h | --help)
      cat <<'EOF'
Usage: ./Ollama.sh [options]

  (default)     Ensure Ollama on http://127.0.0.1:11434, then start Open WebUI (~:8080).
  --ollama-only Ensure Ollama only, then exit (starts ollama serve detached so it keeps running).
  -h, --help    This message.

Requires uv for the default mode (Open WebUI). --ollama-only does not use uv.
EOF
      exit 0
      ;;
    *)
      echo "error: unknown option: $1 (try --help)" >&2
      exit 1
      ;;
  esac
done

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

OLLAMA_PID=""

cleanup() {
  if [[ -n "${OLLAMA_PID:-}" ]] && kill -0 "$OLLAMA_PID" 2>/dev/null; then
    kill "$OLLAMA_PID" 2>/dev/null || true
  fi
  OLLAMA_PID=""
}

ollama_ready() {
  curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1
}

wait_ollama() {
  local max="${1:-60}"
  local i=0
  while (( i < max )); do
    if ollama_ready; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

if ollama_ready; then
  :
elif command -v ollama >/dev/null 2>&1; then
  if [[ "$OLLAMA_ONLY" -eq 1 ]]; then
    echo "🦙 Starting ollama serve (detached) — log: $ROOT/.ollama-serve.log"
    nohup ollama serve >>"$ROOT/.ollama-serve.log" 2>&1 &
    disown 2>/dev/null || true
  else
    ollama serve >>"$ROOT/.ollama-serve.log" 2>&1 &
    OLLAMA_PID=$!
    trap cleanup EXIT INT TERM
  fi
  if ! wait_ollama 60; then
    if [[ -n "${OLLAMA_PID:-}" ]]; then
      cleanup
      trap - EXIT INT TERM 2>/dev/null || true
    fi
    echo "error: Ollama did not become ready on http://127.0.0.1:11434" >&2
    exit 1
  fi
elif [[ "$(uname -s)" == "Darwin" ]]; then
  open -a Ollama 2>/dev/null || true
  if ! wait_ollama 60; then
    cat <<'EOF' >&2
error: Ollama is not responding on http://127.0.0.1:11434

  Install: https://ollama.com/download
  macOS Homebrew: brew bundle (see Brewfile)
EOF
    exit 1
  fi
else
  cat <<'EOF' >&2
error: ollama CLI not found and nothing is listening on http://127.0.0.1:11434

  Install: https://ollama.com/download
EOF
  exit 1
fi

if [[ "$OLLAMA_ONLY" -eq 1 ]]; then
  echo "✅ Ollama is up — http://127.0.0.1:11434"
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is not installed. See https://docs.astral.sh/uv/" >&2
  exit 1
fi

echo "🌐 Starting Open WebUI — http://127.0.0.1:8080/"
export DATA_DIR="${DATA_DIR:-$HOME/.open-webui}"
uv run --with open-webui --with greenlet open-webui serve
