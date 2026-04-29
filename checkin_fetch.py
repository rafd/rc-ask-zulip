import os
import re
from html.parser import HTMLParser

import zulip

from checkin_topics import classify

CHECKIN_STREAM = os.getenv("ZULIP_CHECKIN_STREAM", "checkins")
MAX_PEOPLE = 80
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


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _topic_owner(messages: list[dict], topic_subject: str) -> dict:
    normalized_topic = _normalized(topic_subject)
    for msg in messages:
        if _normalized(msg.get("sender_full_name", "")) == normalized_topic:
            return msg
    return messages[0]


def _thread_preview(messages: list[dict], max_len: int = PREVIEW_LEN) -> str:
    combined_html = " ".join(msg.get("content", "") for msg in messages)
    return make_preview(combined_html, max_len=max_len)


def build_threads(messages: list[dict], max_people: int = MAX_PEOPLE) -> list[dict]:
    """
    Group check-in messages by topic (person thread), newest threads first,
    and return up to max_people thread dicts with inferred thread owner.
    """
    by_topic: dict[str, list[dict]] = {}
    for msg in messages:
        topic_subject = msg.get("subject", "").strip()
        if not topic_subject:
            continue
        by_topic.setdefault(topic_subject, []).append(msg)

    threads: list[dict] = []
    for topic_subject, thread_messages in by_topic.items():
        # Sort messages by timestamp, newest first
        thread_messages.sort(key=lambda m: m["timestamp"], reverse=True)
        
        # Get the owner message
        owner_msg = _topic_owner(thread_messages, topic_subject)
        
        # Add the thread to the list of threads
        threads.append(
            {
                "topic_subject": topic_subject,
                "messages": thread_messages,
                "latest_timestamp": thread_messages[0]["timestamp"],
                "owner_id": owner_msg["sender_id"],
                "owner_name": owner_msg.get("sender_full_name", topic_subject),
                "owner_messages": [
                    m for m in thread_messages if m.get("sender_id") == owner_msg["sender_id"]
                ],
            }
        )

    threads.sort(key=lambda t: t["latest_timestamp"], reverse=True)
    return threads[:max_people]


def dm_url(sender_id: int, zulip_site: str) -> str:
    site = zulip_site.rstrip("/")
    return f"{site}/#narrow/dm/{sender_id}"


def encode_hash_component(text: str) -> str:
    """Zulip web-app encoding for stream/topic fragments in #narrow URLs (matches hash_util)."""
    text = text.replace("%", ".25")

    def repl(m: re.Match[str]) -> str:
        return "." + format(ord(m.group()), "X")

    return re.sub(r"[^\w.\-]", repl, text, flags=re.ASCII)


def checkin_near_url(
    zulip_site: str,
    stream_id: int,
    stream_name: str,
    topic: str,
    message_id: int,
) -> str:
    """Permalink to a message in a channel topic (opens in Zulip web)."""
    site = zulip_site.rstrip("/")
    enc_stream = encode_hash_component(stream_name)
    enc_topic = encode_hash_component(topic)
    return (
        f"{site}/#narrow/channel/{stream_id}-{enc_stream}/topic/{enc_topic}/near/{message_id}"
    )


def suggested_message(name: str, snippet: str) -> str:
    if snippet:
        short = snippet[:60].rsplit(" ", 1)[0] if len(snippet) > 60 else snippet
        return (
            f"Hey {name}! I saw your check-in about {short}… "
            f"— would you be up for pairing sometime?"
        )
    return f"Hey {name}! I'd love to pair with you — would you be up for it?"


def fetch_raw_checkins(num_before: int = 500) -> list[dict]:
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
    Fetch check-ins, group by topic threads (cap 75), classify from thread text,
    and return a dict mapping bucket → list of person dicts.
    """
    raw = fetch_raw_checkins()
    # Zulip returns messages chronologically; reverse so newest is first for grouping.
    raw.sort(key=lambda m: m["timestamp"], reverse=True)
    threads = build_threads(raw)

    buckets: dict[str, list[dict]] = {}
    for thread in threads:
        # Only classify from the thread owner's updates in their own topic.
        # This avoids other people's replies skewing the owner's category.
        preview_source = thread["owner_messages"] or thread["messages"]
        preview = _thread_preview(preview_source)
        matched_buckets = classify(preview + " " + thread["topic_subject"])
        owner_msgs = thread["owner_messages"] or thread["messages"]
        anchor = max(owner_msgs, key=lambda m: m["timestamp"])
        stream_id = anchor.get("stream_id")
        stream_name = anchor.get("display_recipient")
        message_id = anchor.get("id")
        avatar_url = (anchor.get("avatar_url") or "").strip()
        checkin_url = ""
        if (
            stream_id is not None
            and message_id is not None
            and isinstance(stream_name, str)
            and stream_name
        ):
            checkin_url = checkin_near_url(
                zulip_site, int(stream_id), stream_name, thread["topic_subject"], int(message_id)
            )
        entry = {
            "name": thread["owner_name"],
            "user_id": thread["owner_id"],
            "timestamp": thread["latest_timestamp"],
            "topic_subject": thread["topic_subject"],
            "preview": preview,
            "avatar_url": avatar_url,
            "checkin_url": checkin_url,
            "dm_url": dm_url(thread["owner_id"], zulip_site),
            "suggested_message": suggested_message(thread["owner_name"], preview),
        }
        for bucket in matched_buckets:
            buckets.setdefault(bucket, []).append(entry)
    return buckets
