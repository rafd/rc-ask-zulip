import hashlib
import json
import logging
import os

import db
from checkin_topics import classify as regex_classify
from llm_client import build_openai_client

logger = logging.getLogger(__name__)

MAX_LABELS = 5
MAX_LABEL_LEN = 24
LLM_TIMEOUT_SECONDS = 30
DEFAULT_MAX_PARENT_CATEGORIES = 10

SYSTEM_PROMPT = (
    "You categorize Recurse Center check-ins into short topic labels. "
    "Read the check-in text and respond with ONLY a JSON object of the form "
    '{"labels": ["...", "..."]}. Provide 2-5 short labels (each 1-3 words, '
    "Title Case) describing what the person is working on. Prefer broader, "
    "reusable categories over hyper-specific phrases — for a Rust CLI, output "
    '["Rust", "CLI Tools", "Systems"], not ["Rust CLI", "Rust Borrow Checker"]. '
    "Other good examples: \"Rust\", \"Game Engines\", \"AI Agents\", \"Compilers\", "
    '"Music DSP", "Cooking", "Web Frontend", "Distributed Systems". '
    "Prefer the technology, language, or activity over project-specific names. "
    "If the check-in is too vague, return {\"labels\": [\"Other\"]}."
)


CONSOLIDATE_SYSTEM_PROMPT = (
    "You merge a list of topic labels into a small number of broader parent "
    "categories so they group well in a UI. You will be given N labels and a "
    "maximum number of parents. Map EVERY input label to exactly one parent. "
    "Parent names should be short (1-3 words, Title Case) and reusable — prefer "
    'broad domains like "AI", "Systems", "Web", "Music", "Games", "Languages", '
    '"Career", "Life" over project-specific phrases. Respond with ONLY a JSON '
    'object of the form {"mapping": {"<original label>": "<parent>", ...}}.'
)


def _openai_client():
    """Construct the OpenAI-compatible client.

    Raises ExternalLLMNotAllowedError if OPENAI_BASE_URL is set to a blocked
    provider (OpenAI/ChatGPT, Anthropic/Claude, Google Gemini).
    """
    return build_openai_client(timeout=LLM_TIMEOUT_SECONDS)


def _chat_model() -> str:
    return os.environ.get("OPENAI_MODEL", "llama3.1")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _smart_titlecase_word(word: str) -> str:
    """Title-case a single word, but preserve short all-caps acronyms ("AI", "AWS",
    "CLI") and pre-existing mixed-case words ("iOS", "JavaScript")."""
    if not word:
        return word
    # Short all-caps token = acronym; keep as-is.
    if word.isupper() and len(word) <= 4:
        return word
    # Mixed case = author already styled it; keep as-is.
    if any(c.isupper() for c in word) and any(c.islower() for c in word):
        return word
    return word.title()


def _normalize_label(raw: str) -> str:
    cleaned = " ".join(str(raw).split())
    if not cleaned:
        return ""
    if len(cleaned) > MAX_LABEL_LEN:
        cleaned = cleaned[:MAX_LABEL_LEN].rstrip()
    return " ".join(_smart_titlecase_word(w) for w in cleaned.split())


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
    """Ask the local LLM for 2-5 short topic labels. Raises on any failure."""
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


def _consolidation_cache_key(labels: list[str], max_categories: int) -> str:
    canonical = json.dumps(sorted(labels), separators=(",", ":"))
    return "consolidate:v1:" + _hash_text(f"{max_categories}:{canonical}")


def _flatten_mapping(mapping: dict[str, str]) -> list[str]:
    """Round-trip mapping → flat alternating [k, v, k, v] so it fits the existing
    classification_cache table (which stores a JSON list of strings)."""
    flat: list[str] = []
    for k, v in mapping.items():
        flat.append(k)
        flat.append(v)
    return flat


def _unflatten_mapping(flat: list[str]) -> dict[str, str]:
    if len(flat) % 2 != 0:
        return {}
    return {flat[i]: flat[i + 1] for i in range(0, len(flat), 2)}


def consolidate_labels(
    labels: list[str],
    max_categories: int = DEFAULT_MAX_PARENT_CATEGORIES,
) -> dict[str, str]:
    """Ask the LLM to map N labels into <= max_categories parent categories.

    Returns a dict mapping each original label → parent category. Cached by
    sorted-label hash so repeated runs over the same label set are free.
    Every input label is guaranteed to appear as a key in the output (falling
    back to itself if the LLM omitted it).
    """
    unique_labels = sorted({_normalize_label(l) for l in labels if _normalize_label(l)})
    if not unique_labels:
        return {}
    if len(unique_labels) <= max_categories:
        # Already small enough — identity mapping, no LLM needed.
        return {l: l for l in unique_labels}

    cache_key = _consolidation_cache_key(unique_labels, max_categories)
    cached = db.get_classification(cache_key)
    if cached is not None:
        mapping = _unflatten_mapping(cached)
        if mapping:
            for label in unique_labels:
                mapping.setdefault(label, label)
            return mapping

    client = _openai_client()
    user_msg = (
        f"Maximum parents: {max_categories}.\n"
        f"Labels ({len(unique_labels)}):\n"
        + "\n".join(f"- {label}" for label in unique_labels)
    )
    response = client.chat.completions.create(
        model=_chat_model(),
        messages=[
            {"role": "system", "content": CONSOLIDATE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or ""
    parsed = json.loads(content)
    raw_mapping = parsed.get("mapping", {})
    if not isinstance(raw_mapping, dict):
        raise ValueError(
            f"Expected 'mapping' to be a dict, got {type(raw_mapping).__name__}"
        )

    # Normalize. Use a casefold lookup so "rust" / "Rust" both match input labels.
    by_casefold = {l.casefold(): l for l in unique_labels}
    mapping: dict[str, str] = {}
    for raw_orig, raw_parent in raw_mapping.items():
        norm_orig = by_casefold.get(_normalize_label(raw_orig).casefold())
        norm_parent = _normalize_label(raw_parent)
        if norm_orig and norm_parent:
            mapping[norm_orig] = norm_parent

    # Ensure every input label has a destination (fall back to itself if the
    # LLM dropped it).
    for label in unique_labels:
        mapping.setdefault(label, label)

    db.put_classification(cache_key, _flatten_mapping(mapping))
    return mapping


def consolidate_buckets(
    grouped: dict[str, list[dict]],
    max_categories: int = DEFAULT_MAX_PARENT_CATEGORIES,
) -> dict[str, list[dict]]:
    """Reduce a grouped dict to <= max_categories parent buckets.

    Calls consolidate_labels to pick parents, then re-groups entries under
    those parents. Within each parent bucket, dedupes entries by user_id so
    one person whose labels collapse to the same parent doesn't appear twice.
    """
    if not grouped:
        return grouped
    if len(grouped) <= max_categories:
        return grouped

    try:
        mapping = consolidate_labels(list(grouped.keys()), max_categories)
    except Exception as exc:
        logger.warning("Label consolidation failed; keeping unconsolidated buckets: %s", exc)
        return grouped

    out: dict[str, list[dict]] = {}
    seen_user_ids: dict[str, set] = {}
    for original_label, entries in grouped.items():
        parent = mapping.get(_normalize_label(original_label), original_label)
        bucket = out.setdefault(parent, [])
        seen = seen_user_ids.setdefault(parent, set())
        for entry in entries:
            user_id = entry.get("user_id")
            if user_id is not None and user_id in seen:
                continue
            if user_id is not None:
                seen.add(user_id)
            bucket.append(entry)

    # Sort each bucket newest-first by timestamp (it was already roughly newest-
    # first per source bucket, but merging can interleave order).
    for entries in out.values():
        entries.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
    return out
