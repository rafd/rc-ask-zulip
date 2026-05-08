"""Unit tests for checkin_fetch and checkin_topics (no real Zulip calls)."""
import pytest

import checkin_classifier
import db
from checkin_classifier import _normalize_labels, classify_cached, classify_with_llm
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


def test_normalize_labels_caps_at_three():
    assert _normalize_labels(["a", "b", "c", "d", "e"]) == ["A", "B", "C"]


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
