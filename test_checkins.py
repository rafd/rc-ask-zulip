"""Unit tests for checkin_fetch and checkin_topics (no real Zulip calls)."""
import pytest

from checkin_fetch import dedupe_latest, dm_url, make_preview, strip_html, suggested_message
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


# --- dedupe_latest ---

def test_dedupe_latest_keeps_first_seen_as_latest():
    # Messages should be passed sorted newest-first
    msgs = [
        {"sender_id": 1, "timestamp": 200},
        {"sender_id": 1, "timestamp": 100},
        {"sender_id": 2, "timestamp": 150},
    ]
    result = dedupe_latest(msgs)
    assert len(result) == 2
    assert result[0]["timestamp"] == 200  # newer kept


def test_dedupe_latest_cap_at_max_people():
    msgs = [{"sender_id": i, "timestamp": i} for i in range(100)]
    result = dedupe_latest(msgs, max_people=75)
    assert len(result) == 75


def test_dedupe_latest_fewer_than_cap():
    msgs = [{"sender_id": i, "timestamp": i} for i in range(10)]
    result = dedupe_latest(msgs, max_people=75)
    assert len(result) == 10


def test_dedupe_latest_unique_senders_all_kept():
    msgs = [{"sender_id": i, "timestamp": i} for i in range(5)]
    result = dedupe_latest(msgs, max_people=10)
    assert [m["sender_id"] for m in result] == [0, 1, 2, 3, 4]


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
    assert classify("Working on my Rust CLI today") == "Rust"


def test_classify_ai():
    assert classify("Playing with an LLM chatbot") == "AI"


def test_classify_python():
    assert classify("Debugging a Python asyncio issue") == "Python"


def test_classify_games():
    assert classify("Building a game in Godot") == "Games"


def test_classify_music():
    assert classify("Composing music with MIDI") == "Music"


def test_classify_other():
    assert classify("Reading a book today") == "Other"


def test_classify_empty_string():
    assert classify("") == "Other"


def test_classify_case_insensitive():
    assert classify("PYTHON is great") == "Python"


def test_classify_c_standalone_not_matched_in_music():
    # The word "music" contains a "c" but should not classify as C
    assert classify("Making music today") == "Music"


def test_classify_c_standalone_word():
    assert classify("Writing C code with clang") == "C"


def test_classify_math():
    assert classify("Studying some calculus proofs") == "Math"


def test_classify_web():
    assert classify("Building a TypeScript React app") in ("Web",)
