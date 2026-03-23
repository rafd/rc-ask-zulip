import re


CHECKIN_STREAMS = {"checkins", "alumni checkins", "consciousness"}


def _checkin_channel_url_pattern() -> str:
    encoded = [s.replace(" ", ".20") for s in CHECKIN_STREAMS]
    names = "|".join(re.escape(s) for s in encoded)
    return rf'#narrow/channel/\d+-(?:{names})/'


def anonymize_message_content(content: str) -> str:
    """Replace HTML user-mention spans with a plain @mention token,
    and strip links pointing to checkin channels."""
    content = re.sub(
        r'<span class="user-mention[^"]*" data-user-id="(\d+)"[^>]*>@?[^<]*</span>',
        lambda m: f"@user_{m.group(1)}",
        content,
    )
    content = re.sub(
        rf'<a href="{_checkin_channel_url_pattern()}[^"]*">([^<]*)</a>',
        r'\1',
        content,
    )
    return content


def anonymize_checkins(message: dict) -> dict:
    if message.get("display_recipient", "").lower() in CHECKIN_STREAMS:
        return {**message, "subject": "", "match_subject": ""}
    return message


def anonymize_message(message: dict) -> dict:
    return anonymize_checkins({
        **message,
        "sender_email": None,
        "sender_full_name": "",
        "content": anonymize_message_content(message.get("content", "")),
        "match_content": anonymize_message_content(message.get("match_content", "")),
    })
