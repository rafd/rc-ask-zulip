import hashlib
import json
import logging
import os

from openai import OpenAI

import db
from checkin_topics import classify as regex_classify

logger = logging.getLogger(__name__)

MAX_LABELS = 3
MAX_LABEL_LEN = 24
LLM_TIMEOUT_SECONDS = 30

SYSTEM_PROMPT = (
    "You categorize Recurse Center check-ins into short topic labels. "
    "Read the check-in text and respond with ONLY a JSON object of the form "
    '{"labels": ["...", "..."]}. Provide 1-3 short labels (each 1-3 words, '
    "Title Case) describing what the person is working on. Examples: "
    '"Rust", "Game Engines", "AI Agents", "Compilers", "Music DSP", "Cooking". '
    "Prefer the technology, language, or activity over generic words. "
    "If the check-in is too vague, return {\"labels\": [\"Other\"]}."
)


def _openai_client() -> OpenAI:
    local_ollama_base_url = "http://127.0.0.1:11434/v1"
    local_ollama_api_key = "ollama"
    base_url = os.environ.get("OPENAI_BASE_URL", local_ollama_base_url).rstrip("/")
    api_key = os.environ.get("OPENAI_API_KEY", local_ollama_api_key)
    return OpenAI(api_key=api_key, base_url=base_url, timeout=LLM_TIMEOUT_SECONDS)


def _chat_model() -> str:
    return os.environ.get("OPENAI_MODEL", "llama3.1")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_label(raw: str) -> str:
    cleaned = " ".join(str(raw).split())
    if not cleaned:
        return ""
    if len(cleaned) > MAX_LABEL_LEN:
        cleaned = cleaned[:MAX_LABEL_LEN].rstrip()
    return cleaned.title()


def _normalize_labels(labels: list) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in labels:
        label = _normalize_label(raw)
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(label)
        if len(out) >= MAX_LABELS:
            break
    return out


def classify_with_llm(text: str) -> list[str]:
    """Ask the local LLM for 1-3 short topic labels. Raises on any failure."""
    client = _openai_client()
    response = client.chat.completions.create(
        model=_chat_model(),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or ""
    parsed = json.loads(content)
    labels = parsed.get("labels", [])
    if not isinstance(labels, list):
        raise ValueError(f"Expected 'labels' to be a list, got {type(labels).__name__}")
    normalized = _normalize_labels(labels)
    if not normalized:
        raise ValueError("LLM returned no usable labels")
    return normalized


def classify_cached(text: str) -> list[str]:
    """Cached LLM classification with regex fallback on error.

    Cache hit → cached labels. Cache miss → call LLM, cache success.
    On LLM error, fall back to regex_classify and do NOT cache (so a future
    Ollama-up run can populate the cache).
    """
    text_hash = _hash_text(text)
    cached = db.get_classification(text_hash)
    if cached is not None:
        return cached
    try:
        labels = classify_with_llm(text)
    except Exception as exc:
        logger.warning("LLM classify failed, falling back to regex: %s", exc)
        return regex_classify(text)
    db.put_classification(text_hash, labels)
    return labels
