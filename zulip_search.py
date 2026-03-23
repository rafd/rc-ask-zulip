import os
import re

import zulip


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
            "narrow": [{"operator": "search", "operand": query}],
            "anchor": "newest",
            "num_before": 20,
            "num_after": 0,
        },
    )


def anonymize_message_content(content: str) -> str:
    """Replace HTML user-mention spans with a plain @mention token."""
    return re.sub(
        r'<span class="user-mention[^"]*" data-user-id="(\d+)"[^>]*>@?[^<]*</span>',
        lambda m: f"@user_{m.group(1)}",
        content,
    )


def anonymize_message(message: dict) -> dict:
    return {
        **message,
        "sender_email": None,
        "sender_full_name": "",
        "content": anonymize_message_content(message.get("content", "")),
    }


def search_messages_anonymized(query: str) -> dict:
    response = search_messages(query)
    if response.get("result") == "success":
        response = {
            **response,
            "messages": [anonymize_message(m) for m in response.get("messages", [])],
        }
    return response
