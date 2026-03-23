import os

import zulip

from anonymize import anonymize_message


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
                {"operator": "is", "operand": "dm", "negated": True},
                {"operator": "search", "operand": query},
            ],
            "anchor": "newest",
            "num_before": 20,
            "num_after": 0,
        },
    )


def prepare_for_agent(message: dict) -> dict:
    return {
        "content": message["content"],
        "subject": message["subject"],
        "display_recipient": message["display_recipient"],
    }


def anonymize_messages(messages: list[dict]) -> list[dict]:
    return [prepare_for_agent(anonymize_message(m)) for m in messages]


def messages_for_agent(query: str) -> dict:
    response = search_messages(query)
    if response.get("result") == "success":
        response = {
            **response,
            "messages": anonymize_messages(response.get("messages", [])),
        }
    return response
