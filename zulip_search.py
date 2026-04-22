import logging
import os
from datetime import datetime, timezone

import zulip

from anonymize import anonymize_message

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
                {"operator":"channels","operand":"public"},
                {"operator": "search", "operand": query},
            ],
            "allow_empty_topic_name": True,
            "anchor": "newest",
            "num_before": ZULIP_NUM_BEFORE,
            "num_after": 0,
        },
    )

def prepare_for_agent(message: dict) -> dict:
    return {
        "id": message["id"],
        "timestamp": message["timestamp"],
        "content": message["content"],
        "subject": message["subject"],
        "display_recipient": message["display_recipient"],
    }


def anonymize_messages(messages: list[dict]) -> list[dict]:
    return [prepare_for_agent(anonymize_message(m)) for m in messages]


def messages_for_agent(*queries: str) -> list[dict]:
    seen_ids = set()
    results = []
    for query in queries:
        response = search_messages(query)
        if response.get("result") != "success":
            continue
        batch = anonymize_messages(response.get("messages", []))
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


