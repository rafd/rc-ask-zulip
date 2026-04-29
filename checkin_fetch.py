import os
import re
from html.parser import HTMLParser

import zulip

from checkin_topics import classify

CHECKIN_STREAM = os.getenv("ZULIP_CHECKIN_STREAM", "checkins")
MAX_PEOPLE = 75
PREVIEW_LEN = 200


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def strip_html(html_content: str) -> str:
    """Return plain text with HTML tags removed and whitespace collapsed."""
    stripper = _HTMLStripper()
    stripper.feed(html_content)
    return re.sub(r"\s+", " ", stripper.get_text()).strip()


def make_preview(content: str, max_len: int = PREVIEW_LEN) -> str:
    """Plain-text snippet from HTML content, truncated to max_len at a word boundary."""
    text = strip_html(content)
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    return cut + "…"


def dedupe_latest(messages: list[dict], max_people: int = MAX_PEOPLE) -> list[dict]:
    """
    Given messages sorted newest-first, keep the first occurrence per sender_id
    (= their most recent check-in) up to max_people distinct people.
    """
    seen: set[int] = set()
    result: list[dict] = []
    for msg in messages:
        sid = msg["sender_id"]
        if sid in seen:
            continue
        seen.add(sid)
        result.append(msg)
        if len(result) >= max_people:
            break
    return result


def dm_url(sender_id: int, zulip_site: str) -> str:
    site = zulip_site.rstrip("/")
    return f"{site}/#narrow/dm/{sender_id}"


def suggested_message(name: str, snippet: str) -> str:
    if snippet:
        short = snippet[:60].rsplit(" ", 1)[0] if len(snippet) > 60 else snippet
        return (
            f"Hey {name}! I saw your check-in about {short}… "
            f"— would you be up for pairing sometime?"
        )
    return f"Hey {name}! I'd love to pair with you — would you be up for it?"


def fetch_raw_checkins(num_before: int = 400) -> list[dict]:
    client = zulip.Client(
        site=os.environ["ZULIP_SITE"],
        email=os.environ["ZULIP_EMAIL"],
        api_key=os.environ["ZULIP_API_KEY"],
    )
    response = client.call_endpoint(
        url="messages",
        method="GET",
        request={
            "narrow": [{"operator": "channel", "operand": CHECKIN_STREAM}],
            "anchor": "newest",
            "num_before": num_before,
            "num_after": 0,
            "allow_empty_topic_name": True,
        },
    )
    if response.get("result") != "success":
        return []
    return response.get("messages", [])


def build_grouped(zulip_site: str) -> dict[str, list[dict]]:
    """
    Fetch check-ins, dedupe to latest per person (cap 75), classify by topic,
    and return a dict mapping bucket → list of person dicts.
    """
    raw = fetch_raw_checkins()
    # Zulip returns messages chronologically; reverse so newest is first for dedup.
    raw.sort(key=lambda m: m["timestamp"], reverse=True)
    people = dedupe_latest(raw)

    buckets: dict[str, list[dict]] = {}
    for msg in people:
        preview = make_preview(msg.get("content", ""))
        matched_buckets = classify(preview + " " + msg.get("subject", ""))
        entry = {
            "name": msg["sender_full_name"],
            "user_id": msg["sender_id"],
            "timestamp": msg["timestamp"],
            "topic_subject": msg.get("subject", ""),
            "preview": preview,
            "dm_url": dm_url(msg["sender_id"], zulip_site),
            "suggested_message": suggested_message(msg["sender_full_name"], preview),
        }
        for bucket in matched_buckets:
            buckets.setdefault(bucket, []).append(entry)
    return buckets
