"""Unit tests for checkin_fetch and checkin_topics (no real Zulip calls)."""
import pytest

import checkin_classifier
import db
from checkin_classifier import (
    _normalize_labels,
    classify_cached,
    classify_with_llm,
    consolidate_buckets,
    consolidate_labels,
)
from checkin_fetch import (
    build_grouped,
    build_threads,
    checkin_near_url,
    dm_url,
    encode_hash_component,
    make_preview,
    strip_html,
    suggested_message,
)
from checkin_topics import classify
from llm_client import (
    ExternalLLMNotAllowedError,
    assert_not_blocked_provider,
    build_openai_client,
)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point db at a fresh sqlite file and init the schema."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()
    yield db_path


# --- strip_html ---

def test_strip_html_removes_tags():
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_plain_text_unchanged():
    assert strip_html("No HTML here") == "No HTML here"


def test_strip_html_collapses_whitespace():
    assert strip_html("<p>  lots   of   spaces  </p>") == "lots of spaces"


def test_strip_html_empty_string():
    assert strip_html("") == ""


def test_strip_html_nested_tags():
    assert strip_html("<div><span>hello</span> <em>there</em></div>") == "hello there"


# --- make_preview ---

def test_make_preview_short_text_unchanged():
    assert make_preview("short text") == "short text"


def test_make_preview_strips_html():
    assert make_preview("<p>hello world</p>") == "hello world"


def test_make_preview_truncates_at_word_boundary():
    # 60 chars of "word " = 12 repetitions
    long_text = "word " * 60  # 300 chars
    result = make_preview(long_text, max_len=20)
    assert len(result) <= 25  # ellipsis adds 1 char
    assert result.endswith("…")
    assert not result.endswith(" …")  # no trailing space before ellipsis


def test_make_preview_exact_max_len_no_truncation():
    text = "a" * 200
    result = make_preview(text, max_len=200)
    assert result == text
    assert not result.endswith("…")


# --- build_threads ---

def test_build_threads_groups_all_messages_by_topic():
    msgs = [
        {"sender_id": 1, "sender_full_name": "Alice", "subject": "Alice", "timestamp": 300, "content": "<p>first</p>"},
        {"sender_id": 2, "sender_full_name": "Bob", "subject": "Bob", "timestamp": 200, "content": "<p>other</p>"},
        {"sender_id": 1, "sender_full_name": "Alice", "subject": "Alice", "timestamp": 100, "content": "<p>second</p>"},
    ]
    result = build_threads(msgs, max_people=10)
    assert len(result) == 2
    alice = next(t for t in result if t["topic_subject"] == "Alice")
    assert len(alice["messages"]) == 2
    assert alice["latest_timestamp"] == 300


def test_build_threads_cap_at_max_people():
    msgs = [
        {
            "sender_id": i,
            "sender_full_name": f"Person {i}",
            "subject": f"Person {i}",
            "timestamp": i,
            "content": "<p>msg</p>",
        }
        for i in range(100)
    ]
    result = build_threads(msgs, max_people=75)
    assert len(result) == 75


def test_build_threads_owner_matches_topic_name_even_if_latest_message_is_not_owner():
    msgs = [
        {
            "sender_id": 2,
            "sender_full_name": "Bob",
            "subject": "Alice",
            "timestamp": 300,
            "content": "<p>reply</p>",
        },
        {
            "sender_id": 1,
            "sender_full_name": "Alice",
            "subject": "Alice",
            "timestamp": 200,
            "content": "<p>owner message</p>",
        },
    ]
    result = build_threads(msgs, max_people=10)
    assert result[0]["owner_id"] == 1
    assert result[0]["owner_name"] == "Alice"


def test_build_threads_owner_falls_back_to_latest_message_sender():
    msgs = [
        {
            "sender_id": 2,
            "sender_full_name": "Bob",
            "subject": "Alice",
            "timestamp": 300,
            "content": "<p>latest</p>",
        },
        {
            "sender_id": 3,
            "sender_full_name": "Carol",
            "subject": "Alice",
            "timestamp": 200,
            "content": "<p>older</p>",
        },
    ]
    result = build_threads(msgs, max_people=10)
    assert result[0]["owner_id"] == 2
    assert result[0]["owner_name"] == "Bob"


def test_build_grouped_classifies_from_owner_messages_only(monkeypatch):
    msgs = [
        {
            "id": 1003,
            "sender_id": 1,
            "sender_full_name": "Alice",
            "subject": "Alice",
            "timestamp": 300,
            "content": "<p>Working on Rust borrow checker examples.</p>",
            "stream_id": 41,
            "display_recipient": "checkins",
            "avatar_url": "https://example.com/a.png",
        },
        {
            "id": 1002,
            "sender_id": 2,
            "sender_full_name": "Bob",
            "subject": "Alice",
            "timestamp": 250,
            "content": "<p>I am training an LLM with embeddings.</p>",
            "stream_id": 41,
            "display_recipient": "checkins",
            "avatar_url": "",
        },
    ]

    monkeypatch.setattr("checkin_fetch.fetch_raw_checkins", lambda: msgs)
    grouped = build_grouped("https://recurse.zulipchat.com")

    assert "Rust" in grouped
    assert "AI" not in grouped
    assert grouped["Rust"][0]["name"] == "Alice"
    assert grouped["Rust"][0]["avatar_url"] == "https://example.com/a.png"
    assert grouped["Rust"][0]["checkin_url"].endswith("/near/1003")


# --- encode_hash_component / checkin_near_url ---

def test_encode_hash_component_space():
    assert encode_hash_component("Alice Smith") == "Alice.20Smith"


def test_encode_hash_component_percent():
    assert ".25" in encode_hash_component("100% done")


def test_checkin_near_url_shape():
    url = checkin_near_url(
        "https://recurse.zulipchat.com",
        41,
        "checkins",
        "Alice",
        999001,
    )
    assert url.startswith("https://recurse.zulipchat.com/#narrow/channel/41-checkins/topic/Alice/near/999001")


# --- dm_url ---

def test_dm_url_basic():
    assert dm_url(42, "https://recurse.zulipchat.com") == "https://recurse.zulipchat.com/#narrow/dm/42"


def test_dm_url_strips_trailing_slash():
    assert dm_url(42, "https://recurse.zulipchat.com/") == "https://recurse.zulipchat.com/#narrow/dm/42"


# --- suggested_message ---

def test_suggested_message_with_snippet():
    msg = suggested_message("Alice", "working on a Rust CLI")
    assert "Alice" in msg
    assert "working on a Rust CLI" in msg


def test_suggested_message_empty_snippet():
    msg = suggested_message("Bob", "")
    assert "Bob" in msg
    # Should still be a meaningful sentence
    assert len(msg) > 10


# --- classify ---

def test_classify_rust():
    assert classify("Working on my Rust CLI today") == ["Rust"]


def test_classify_ai():
    assert classify("Playing with an LLM chatbot") == ["AI"]


def test_classify_python():
    assert classify("Debugging a Python asyncio issue") == ["Python"]


def test_classify_games():
    assert classify("Building a game in Godot") == ["Games"]


def test_classify_music():
    assert classify("Composing music with MIDI") == ["Music"]


def test_classify_other():
    assert classify("Reading a book today") == ["Other"]


def test_classify_empty_string():
    assert classify("") == ["Other"]


def test_classify_case_insensitive():
    assert classify("PYTHON is great") == ["Python"]


def test_classify_c_standalone_not_matched_in_music():
    # The word "music" contains a "c" but should not classify as C
    assert classify("Making music today") == ["Music"]


def test_classify_c_standalone_word():
    assert classify("Writing C code with clang") == ["C"]


def test_classify_math():
    assert classify("Studying some calculus proofs") == ["Math"]


def test_classify_web():
    assert classify("Building a TypeScript React app") == ["Web"]


def test_classify_multiple_buckets():
    result = classify("Building a Python API on AWS with Docker and React")
    assert result == ["Web", "Python", "DevOps", "Cloud"]


# --- _normalize_labels ---

def test_normalize_labels_titlecases_and_dedupes():
    assert _normalize_labels(["rust", "Rust", "  Game Engines  "]) == ["Rust", "Game Engines"]


def test_normalize_labels_caps_at_max():
    # MAX_LABELS = 5; extra inputs are dropped.
    assert _normalize_labels(["a", "b", "c", "d", "e", "f", "g"]) == [
        "A", "B", "C", "D", "E",
    ]


def test_normalize_labels_drops_empty():
    assert _normalize_labels(["", "  ", "Music"]) == ["Music"]


def test_normalize_labels_truncates_long():
    long_label = "A" * 100
    result = _normalize_labels([long_label])
    assert len(result) == 1
    assert len(result[0]) <= 24


# --- classify_with_llm ---

class _FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeChat:
    def __init__(self, content_or_exc):
        self._content_or_exc = content_or_exc

    def create(self, **kwargs):
        if isinstance(self._content_or_exc, Exception):
            raise self._content_or_exc
        return _FakeResponse(self._content_or_exc)


class _FakeOpenAI:
    def __init__(self, content_or_exc):
        self.chat = type("C", (), {"completions": _FakeChat(content_or_exc)})()


def test_classify_with_llm_parses_and_normalizes(monkeypatch):
    monkeypatch.setattr(
        checkin_classifier,
        "_openai_client",
        lambda: _FakeOpenAI('{"labels": ["rust", "cli tools"]}'),
    )
    assert classify_with_llm("anything") == ["Rust", "Cli Tools"]


def test_classify_with_llm_raises_on_missing_labels(monkeypatch):
    monkeypatch.setattr(
        checkin_classifier,
        "_openai_client",
        lambda: _FakeOpenAI('{"labels": []}'),
    )
    with pytest.raises(ValueError):
        classify_with_llm("anything")


def test_classify_with_llm_raises_on_bad_json(monkeypatch):
    monkeypatch.setattr(
        checkin_classifier,
        "_openai_client",
        lambda: _FakeOpenAI("not json"),
    )
    with pytest.raises(Exception):
        classify_with_llm("anything")


# --- classify_cached ---

def test_classify_cached_returns_cached_value_without_calling_llm(temp_db, monkeypatch):
    calls = {"n": 0}

    def fake_llm(text):
        calls["n"] += 1
        return ["Rust"]

    monkeypatch.setattr(checkin_classifier, "classify_with_llm", fake_llm)

    first = classify_cached("hello world")
    second = classify_cached("hello world")

    assert first == ["Rust"]
    assert second == ["Rust"]
    assert calls["n"] == 1  # second call hit the cache


def test_classify_cached_falls_back_to_regex_on_llm_error(temp_db, monkeypatch):
    def fake_llm(text):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(checkin_classifier, "classify_with_llm", fake_llm)

    result = classify_cached("Working on my Rust CLI today")
    assert result == ["Rust"]  # regex fallback

    # Should NOT cache the fallback result, so a recovered LLM is used next time.
    monkeypatch.setattr(checkin_classifier, "classify_with_llm", lambda t: ["Recovered"])
    assert classify_cached("Working on my Rust CLI today") == ["Recovered"]


# --- db snapshot helpers ---

def test_snapshot_round_trip(temp_db):
    grouped = {"Rust": [{"name": "Alice"}], "AI": [{"name": "Bob"}]}
    db.put_snapshot(grouped)
    result = db.get_snapshot()
    assert result is not None
    loaded, created_at = result
    assert loaded == grouped
    assert isinstance(created_at, str) and len(created_at) > 0


def test_snapshot_overwrites_previous(temp_db):
    db.put_snapshot({"A": []})
    db.put_snapshot({"B": [{"name": "Carol"}]})
    loaded, _ = db.get_snapshot()
    assert loaded == {"B": [{"name": "Carol"}]}


def test_snapshot_returns_none_when_empty(temp_db):
    assert db.get_snapshot() is None


# --- build_grouped honors classify_fn ---

def test_build_grouped_uses_classify_fn(monkeypatch):
    msgs = [
        {
            "id": 1,
            "sender_id": 1,
            "sender_full_name": "Alice",
            "subject": "Alice",
            "timestamp": 100,
            "content": "<p>Anything goes here.</p>",
            "stream_id": 41,
            "display_recipient": "checkins",
            "avatar_url": "",
        },
    ]
    monkeypatch.setattr("checkin_fetch.fetch_raw_checkins", lambda: msgs)

    def fake_classify(text):
        return ["Custom Bucket"]

    grouped = build_grouped("https://recurse.zulipchat.com", classify_fn=fake_classify)
    assert "Custom Bucket" in grouped
    assert grouped["Custom Bucket"][0]["name"] == "Alice"


# --- consolidate_labels ---

def test_consolidate_labels_skips_llm_when_already_small(temp_db, monkeypatch):
    """If we have <= max_categories, no LLM call is needed — identity mapping."""
    called = {"n": 0}

    def fake_client():
        called["n"] += 1
        raise AssertionError("LLM should not be called for small label sets")

    monkeypatch.setattr(checkin_classifier, "_openai_client", fake_client)
    mapping = consolidate_labels(["Rust", "AI", "Music"], max_categories=10)
    # Smart titlecase preserves "AI" as an acronym.
    assert mapping == {"Rust": "Rust", "AI": "AI", "Music": "Music"}
    assert called["n"] == 0


def test_consolidate_labels_calls_llm_and_caches(temp_db, monkeypatch):
    """For >max labels, the LLM is called once and the result is cached."""
    labels = ["Rust CLI", "Rust Borrow", "AI Agents", "LLM Tooling",
              "Game Dev", "Pygame", "Music DSP", "Synth", "Web", "CSS", "React"]
    fake_response = '''{"mapping": {
        "Rust CLI": "Systems",
        "Rust Borrow": "Systems",
        "AI Agents": "AI",
        "LLM Tooling": "AI",
        "Game Dev": "Games",
        "Pygame": "Games",
        "Music DSP": "Music",
        "Synth": "Music",
        "Web": "Web",
        "CSS": "Web",
        "React": "Web"
    }}'''
    calls = {"n": 0}

    def fake_client_factory():
        calls["n"] += 1
        return _FakeOpenAI(fake_response)

    monkeypatch.setattr(checkin_classifier, "_openai_client", fake_client_factory)
    mapping = consolidate_labels(labels, max_categories=5)
    assert mapping["Rust CLI"] == "Systems"
    assert mapping["AI Agents"] == "AI"  # acronym preserved
    assert calls["n"] == 1

    # Same input again: served from cache, no second LLM call.
    mapping2 = consolidate_labels(labels, max_categories=5)
    assert mapping2 == mapping
    assert calls["n"] == 1


def test_consolidate_labels_falls_back_for_missing_labels(temp_db, monkeypatch):
    """If the LLM omits some input labels, missing ones map to themselves."""
    labels = [f"Label {i}" for i in range(15)]
    # Mapping covers only the first three.
    partial_response = '{"mapping": {"Label 0": "A", "Label 1": "A", "Label 2": "B"}}'
    monkeypatch.setattr(
        checkin_classifier, "_openai_client",
        lambda: _FakeOpenAI(partial_response),
    )
    mapping = consolidate_labels(labels, max_categories=5)
    assert mapping["Label 0"] == "A"
    assert mapping["Label 1"] == "A"
    assert mapping["Label 2"] == "B"
    # Untouched labels fall back to themselves.
    for i in range(3, 15):
        assert mapping[f"Label {i}"] == f"Label {i}"


# --- consolidate_buckets ---

def test_consolidate_buckets_noop_when_already_small(temp_db, monkeypatch):
    monkeypatch.setattr(
        checkin_classifier, "_openai_client",
        lambda: pytest.fail("LLM should not be called"),
    )
    grouped = {"Rust": [{"user_id": 1}], "AI": [{"user_id": 2}]}
    assert consolidate_buckets(grouped, max_categories=10) == grouped


def test_consolidate_buckets_merges_and_dedupes_per_user(temp_db, monkeypatch):
    """Two labels for the same person collapse into a single parent entry."""
    grouped = {
        "Rust CLI": [{"user_id": 1, "name": "Alice", "timestamp": 200}],
        "Rust Borrow": [{"user_id": 1, "name": "Alice", "timestamp": 200}],
        "AI Agents": [{"user_id": 2, "name": "Bob", "timestamp": 100}],
        "LLM Tooling": [{"user_id": 2, "name": "Bob", "timestamp": 100}],
        "Game Dev": [{"user_id": 3, "name": "Carol", "timestamp": 50}],
        "Pygame": [{"user_id": 3, "name": "Carol", "timestamp": 50}],
        "Music DSP": [{"user_id": 4, "name": "Dan", "timestamp": 30}],
        "Synth": [{"user_id": 4, "name": "Dan", "timestamp": 30}],
        "Web": [{"user_id": 5, "name": "Eve", "timestamp": 20}],
        "CSS": [{"user_id": 5, "name": "Eve", "timestamp": 20}],
        "React": [{"user_id": 6, "name": "Frank", "timestamp": 10}],
    }
    fake_response = '''{"mapping": {
        "Rust CLI": "Systems",
        "Rust Borrow": "Systems",
        "AI Agents": "AI",
        "LLM Tooling": "AI",
        "Game Dev": "Games",
        "Pygame": "Games",
        "Music DSP": "Music",
        "Synth": "Music",
        "Web": "Web",
        "CSS": "Web",
        "React": "Web"
    }}'''
    monkeypatch.setattr(
        checkin_classifier, "_openai_client",
        lambda: _FakeOpenAI(fake_response),
    )
    out = consolidate_buckets(grouped, max_categories=5)

    assert len(out) <= 5
    # Alice appeared in 2 source buckets that map to the same parent → 1 entry.
    systems = out.get("Systems", [])
    assert sum(1 for e in systems if e["user_id"] == 1) == 1
    # Frank is alone in "React" → mapped to "Web".
    web = out.get("Web", [])
    assert any(e["user_id"] == 6 for e in web)
    # No bucket has duplicate user_ids.
    for parent, entries in out.items():
        ids = [e["user_id"] for e in entries]
        assert len(ids) == len(set(ids)), f"Duplicates in {parent}: {ids}"


def test_consolidate_buckets_returns_input_on_empty():
    assert consolidate_buckets({}) == {}


def test_consolidate_buckets_returns_input_on_llm_error(temp_db, monkeypatch):
    """If consolidate_labels raises, fall back to the unconsolidated grouped dict."""
    grouped = {f"Label {i}": [{"user_id": i}] for i in range(15)}

    def fake_client():
        raise RuntimeError("ollama down")

    monkeypatch.setattr(checkin_classifier, "_openai_client", fake_client)
    out = consolidate_buckets(grouped, max_categories=5)
    assert out == grouped


# --- llm_client.assert_not_blocked_provider ---

@pytest.mark.parametrize("url", [
    # Local
    "http://127.0.0.1:11434/v1",
    "http://localhost:11434/v1",
    "http://[::1]:11434/v1",
    # Private network — fine
    "http://192.168.1.5:11434/v1",
    "http://10.0.0.7:11434/v1",
    # Arbitrary public hosts that aren't on the denylist — fine
    "https://api.groq.com/openai/v1",
    "https://api.together.xyz/v1",
    "https://example.com/v1",
    "http://8.8.8.8/v1",
    # Lookalikes that should NOT match (suffix boundary check)
    "https://myopenai.com/v1",
    "https://notanthropic.com/v1",
])
def test_assert_not_blocked_provider_allows_non_blocked(url):
    assert_not_blocked_provider(url) is None


@pytest.mark.parametrize("url", [
    # OpenAI / ChatGPT
    "https://api.openai.com/v1",
    "https://API.OpenAI.com/v1",                  # case-insensitive
    "https://chat.openai.com/api",
    # Anthropic / Claude
    "https://api.anthropic.com/v1",
    "https://claude.ai/api",
    # Google Gemini / Vertex
    "https://generativelanguage.googleapis.com/v1",
    "https://aiplatform.googleapis.com/v1",
])
def test_assert_not_blocked_provider_rejects_blocked(url):
    with pytest.raises(ExternalLLMNotAllowedError):
        assert_not_blocked_provider(url)


def test_assert_not_blocked_provider_rejects_unparseable():
    with pytest.raises(ExternalLLMNotAllowedError):
        assert_not_blocked_provider("not a url")


def test_assert_not_blocked_provider_error_message_is_actionable():
    """The error should name the matched provider suffix."""
    with pytest.raises(ExternalLLMNotAllowedError, match=r"openai\.com"):
        assert_not_blocked_provider("https://api.openai.com/v1")


# --- llm_client.build_openai_client ---

def test_build_openai_client_uses_local_default(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = build_openai_client()
    assert "127.0.0.1" in str(client.base_url)


def test_build_openai_client_raises_for_chatgpt(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    with pytest.raises(ExternalLLMNotAllowedError):
        build_openai_client()


def test_build_openai_client_raises_for_claude(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.anthropic.com/v1")
    with pytest.raises(ExternalLLMNotAllowedError):
        build_openai_client()


def test_build_openai_client_raises_for_gemini(monkeypatch):
    monkeypatch.setenv(
        "OPENAI_BASE_URL", "https://generativelanguage.googleapis.com/v1"
    )
    with pytest.raises(ExternalLLMNotAllowedError):
        build_openai_client()


def test_build_openai_client_allows_arbitrary_remote(monkeypatch):
    """Non-blocked remote endpoints (Groq, Together, self-hosted) work fine."""
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    client = build_openai_client()
    assert "groq.com" in str(client.base_url)


def test_build_openai_client_accepts_local_override(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    client = build_openai_client()
    assert "localhost" in str(client.base_url)
