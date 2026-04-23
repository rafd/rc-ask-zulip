#!/bin/bash

# Install Python dependencies (uv) for Ask RC Zulip.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "-=-=-=-=- 🚀 Installing Python dependencies... -=-=-=-=-"

if ! command -v uv &> /dev/null; then
  echo "❌ uv not found. Install it first:"
  echo "   https://docs.astral.sh/uv/getting-started/installation/"
  echo "   macOS: brew install uv"
  exit 1
fi

echo "-=-=-=-=- 📥 uv sync ( getting dependencies and setting up virtual-environment) -=-=-=-=-"
uv sync

if [[ "${1:-}" == "--brew" ]]; then
  if command -v brew &> /dev/null && [[ -f "$SCRIPT_DIR/Brewfile" ]]; then
    echo "-=-=-=-=- 🍺 brew bundle: install/upgrade Homebrew packages from Brewfile (here: Ollama) -=-=-=-=-"
    brew bundle
  elif ! command -v brew &> /dev/null; then
    echo "⚠️  --brew was passed but Homebrew is not installed (https://brew.sh/)"
  else
    echo "⚠️  No Brewfile in $SCRIPT_DIR; skipping brew bundle"
  fi
fi

echo "✅ Done."
