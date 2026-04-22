#!/usr/bin/env bash
# Require Homebrew and run `brew bundle` in this repo (Ollama, etc. from Brewfile).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if ! command -v brew >/dev/null 2>&1; then
  echo "error: Homebrew not found (https://brew.sh/)" >&2
  exit 1
fi

if [[ ! -f "$ROOT/Brewfile" ]]; then
  echo "error: Brewfile not found in $ROOT" >&2
  exit 1
fi

brew bundle
