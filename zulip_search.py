import logging
import os
from datetime import datetime, timezone

import zulip

logger = logging.getLogger(__name__)

# Max messages returned per search query (Zulip API num_before).
ZULIP_NUM_BEFORE = 30


def search_messages(query: str) -> dict:
    client = zulip.Client(
        site=os.environ["ZULIP_SITE"],
        email=os.environ["ZULIP_EMAIL"],
        api_key=os.environ["ZULIP_API_KEY"],
    )
    return client.call_endpoint(
        url="messages",
        method="GET",
        request={
            "narrow": [
                {"operator": "channels", "operand": "public"},
                {"operator": "search", "operand": query},
            ],
            "allow_empty_topic_name": True,
            "anchor": "newest",
            "num_before": ZULIP_NUM_BEFORE,
            "num_after": 0,
        },
    )


def prepare_for_agent(message: dict) -> dict:
    """Pick fields for the LLM and UI. No redaction (local/trusted use)."""
    out: dict = {
        "id": message["id"],
        "timestamp": message["timestamp"],
        "content": message.get("content", ""),
        "subject": message.get("subject", ""),
        "display_recipient": message.get("display_recipient", ""),
        "sender_full_name": message.get("sender_full_name", ""),
        "sender_email": message.get("sender_email", ""),
    }
    if message.get("stream_id") is not None:
        out["stream_id"] = message["stream_id"]
    return out


def messages_for_agent(*queries: str) -> list[dict]:
    seen_ids = set()
    results = []
    for query in queries:
        response = search_messages(query)
        if response.get("result") != "success":
            continue
        batch = [prepare_for_agent(m) for m in response.get("messages", [])]
        if batch:
            earliest = min(m["timestamp"] for m in batch)
            latest = max(m["timestamp"] for m in batch)
            fmt = lambda ts: datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            logger.info("search %r: %d results, %s – %s", query, len(batch), fmt(earliest), fmt(latest))
        else:
            logger.info("search %r: 0 results", query)
        for message in batch:
            if message["id"] not in seen_ids:
                seen_ids.add(message["id"])
                results.append(message)
    results.sort(key=lambda m: m["timestamp"])
    return results


