#!/usr/bin/env bash
# Local dev entrypoint: install deps (uv), optional Ollama via Homebrew, run the FastAPI app.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# Set only when this script starts `ollama serve`; trap kills this PID on exit.
RUNSH_OLLAMA_SERVE_PID=""

usage() {
  cat <<'EOF'
Usage: ./run.sh <command>

  setup        Install Python deps (uv sync). On macOS, suggests "brew bundle" for Ollama.
  setup --brew Same as setup, then run `brew bundle` when brew and Brewfile exist.
  Ollama only: ./setup_ollama.sh [--brew]  (install CLI + pull OPENAI_MODEL; see that file)
  pull-model   Run `ollama pull` for OPENAI_MODEL (default: llama3.1).
  run          Start the API dev server with reload (default)

Requires uv: https://docs.astral.sh/uv/

Environment (Zulip — required for search):
  ZULIP_SITE, ZULIP_EMAIL, ZULIP_API_KEY

Environment (LLM — defaults target local Ollama):
  OPENAI_BASE_URL   default http://127.0.0.1:11434/v1
  OPENAI_API_KEY    default ollama (ignored by Ollama)
  OPENAI_MODEL      default llama3.1
  SKIP_OLLAMA_CHECK=1   Skip Ollama preflight and auto-start (e.g. remote API)
  OLLAMA_AUTOSTART=0    Require Ollama already running; do not start it from this script

When ./run.sh run starts `ollama serve` itself, stopping the dev server (exit or Ctrl+C)
stops that Ollama process. If the macOS app was used instead (open -a Ollama), the app
keeps running.
EOF
}

cleanup_runsh_ollama_serve() {
  if [[ -n "${RUNSH_OLLAMA_SERVE_PID:-}" ]]; then
    if kill -0 "$RUNSH_OLLAMA_SERVE_PID" 2>/dev/null; then
      kill "$RUNSH_OLLAMA_SERVE_PID" 2>/dev/null || true
    fi
    RUNSH_OLLAMA_SERVE_PID=""
  fi
}

need_ollama_preflight() {
  if [[ "${SKIP_OLLAMA_CHECK:-}" == "1" ]]; then
    return 1
  fi
  local base="${OPENAI_BASE_URL:-}"
  if [[ -n "$base" ]]; then
    if [[ "$base" != *"127.0.0.1:11434"* ]] && [[ "$base" != *"localhost:11434"* ]]; then
      return 1
    fi
  fi
  return 0
}

ollama_api_ready() {
  curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1
}

wait_for_ollama() {
  local max="${1:-60}"
  local i=0
  while (( i < max )); do
    if ollama_api_ready; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

print_ollama_error() {
  cat <<'EOF' >&2
error: Ollama does not appear to be running on http://127.0.0.1:11434

  Install: https://ollama.com/download
  macOS: open the Ollama app, or run: ollama serve
  Linux: ollama serve
  On macOS with Homebrew: brew bundle  (see Brewfile)

To require a running server without auto-start: OLLAMA_AUTOSTART=0 ./run.sh run
To skip this entirely (e.g. remote OPENAI_BASE_URL): SKIP_OLLAMA_CHECK=1 ./run.sh run
EOF
}

ensure_ollama_running() {
  if ! need_ollama_preflight; then
    return 0
  fi
  if ollama_api_ready; then
    return 0
  fi
  if [[ "${OLLAMA_AUTOSTART:-1}" == "0" ]]; then
    print_ollama_error
    return 1
  fi

  if command -v ollama >/dev/null 2>&1; then
    ollama serve >>"$ROOT/.ollama-serve.log" 2>&1 &
    RUNSH_OLLAMA_SERVE_PID=$!
    trap cleanup_runsh_ollama_serve EXIT INT TERM
    if wait_for_ollama 60; then
      return 0
    fi
    cleanup_runsh_ollama_serve
    trap - EXIT INT TERM
    RUNSH_OLLAMA_SERVE_PID=""
  fi

  if [[ "$(uname -s)" == "Darwin" ]]; then
    open -a Ollama 2>/dev/null || true
    if wait_for_ollama 60; then
      return 0
    fi
  fi

  print_ollama_error
  return 1
}

cmd="${1:-run}"

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
    uv sync --extra dev
    if [[ "${2:-}" == "--brew" ]]; then
      if command -v brew >/dev/null 2>&1 && [[ -f Brewfile ]]; then
        brew bundle
      elif ! command -v brew >/dev/null 2>&1; then
        echo "warning: Homebrew not found; install Ollama from https://ollama.com/download" >&2
      fi
    elif [[ -f Brewfile ]]; then
      echo "tip: install Ollama on macOS with Homebrew: brew bundle  (or: ./run.sh setup --brew)"
    fi
    ;;
  pull-model)
    if ! command -v ollama >/dev/null 2>&1; then
      echo "error: ollama CLI not found. Install from https://ollama.com/download" >&2
      exit 1
    fi
    model="${OPENAI_MODEL:-llama3.1}"
    exec ollama pull "$model"
    ;;
  run)
    ensure_ollama_running
    uv run python main.py
    ;;
  *)
    echo "error: unknown command: $cmd" >&2
    usage
    exit 1
    ;;
esac
