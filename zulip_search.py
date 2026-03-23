import os

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
