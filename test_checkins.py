"""Unit tests for checkin_fetch and checkin_topics (no real Zulip calls)."""
import pytest

from checkin_fetch import build_grouped, build_threads, dm_url, make_preview, strip_html, suggested_message
from checkin_topics import classify


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
            "sender_id": 1,
            "sender_full_name": "Alice",
            "subject": "Alice",
            "timestamp": 300,
            "content": "<p>Working on Rust borrow checker examples.</p>",
        },
        {
            "sender_id": 2,
            "sender_full_name": "Bob",
            "subject": "Alice",
            "timestamp": 250,
            "content": "<p>I am training an LLM with embeddings.</p>",
        },
    ]

    monkeypatch.setattr("checkin_fetch.fetch_raw_checkins", lambda: msgs)
    grouped = build_grouped("https://recurse.zulipchat.com")

    assert "Rust" in grouped
    assert "AI" not in grouped
    assert grouped["Rust"][0]["name"] == "Alice"


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
