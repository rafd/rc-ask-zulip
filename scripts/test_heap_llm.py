#!/usr/bin/env python3
"""Smoke-test the heap-LLM OpenAI-compatible endpoint (standalone).

Usage (from repo root):
  uv run python scripts/test_heap_llm.py

Requires OPENAI_API_KEY in the environment (or in .env).
Optional: LLM_MODEL (default: gemma3:12b).
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

BASE_URL = "https://heap-llm.rcdis.co/api"
QUESTION = "Why is the sky green"


def main() -> int:
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Missing OPENAI_API_KEY (set it or add to .env).", file=sys.stderr)
        return 1

    model = os.environ.get("LLM_MODEL", "llama3.1:8b" )#"gemma3:12b"
    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    print(f"base_url={BASE_URL!r} model={model!r}", flush=True)
    print(f"user: {QUESTION!r}\n", flush=True)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": QUESTION}],
        )
    except Exception as e:
        print(f"Request failed: {e!r}", file=sys.stderr)
        return 1

    choices = response.choices or []
    if not choices:
        print("No choices in response.", file=sys.stderr)
        return 1

    content = choices[0].message.content
    if content is None:
        print("Assistant message has no text content.", file=sys.stderr)
        return 1

    print("assistant:", flush=True)
    print(content, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
