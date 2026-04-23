import json
import logging
import os
import uuid

from openai import OpenAI

logger = logging.getLogger(__name__)

from zulip_search import messages_for_agent


class AgentAnswerError(Exception):
    """Raised when the model never returns a valid structured answer."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _openai_client() -> OpenAI:
    LOCAL_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
    LOCAL_OLLAMA_API_KEY = "ollama"
    base_url = os.environ.get("OPENAI_BASE_URL", LOCAL_OLLAMA_BASE_URL).rstrip("/")
    api_key = os.environ.get("OPENAI_API_KEY", LOCAL_OLLAMA_API_KEY)
    return OpenAI(api_key=api_key, base_url=base_url)


def _chat_model() -> str:
    LOCAL_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
    return LOCAL_OLLAMA_MODEL

SYSTEM_PROMPT = """\
You are an expert research assistant that answers questions about what Recurse Center participants think about topics.

## Search
You already have an initial batch of Zulip messages from a search on the user's question. Use the tool \
`messages_for_agent` for additional searches if needed: different phrasings, synonyms, or narrower terms. \
Prefer quality over quantity (a few dozen on-topic messages is usually enough).

## Answer format (required)
Respond with ONLY a JSON object (no markdown fences, no commentary) with exactly these keys: \
section_1, section_2, section_3.

Each section is an object with:
- "heading": short title for that theme
- "text": executive summary using concise bullet lines (markdown-friendly plain text; use "- " bullets)
- "citations": array of objects {"message_id": <integer>, "quote": "<short verbatim excerpt>"}

Rules:
- Cover three distinct themes across section_1, section_2, section_3.
- In "text", summarize; do not paste full Zulip messages.
- Every "quote" must be a short verbatim excerpt (at most ~40 words or two sentences) from a message the user can find by message_id.
- Use only message_id values that appear in the search/tool results you have seen.
"""


_SECTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "heading": {"type": "string"},
        "text": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "integer"},
                    "quote": {"type": "string"},
                },
                "required": ["message_id", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["heading", "text", "citations"],
    "additionalProperties": False,
}

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "answer_three_sections",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "section_1": _SECTION_JSON_SCHEMA,
                "section_2": _SECTION_JSON_SCHEMA,
                "section_3": _SECTION_JSON_SCHEMA,
            },
            "required": ["section_1", "section_2", "section_3"],
            "additionalProperties": False,
        },
    },
}



TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "messages_for_agent",
        "description": (
            "Search Zulip conversations at the Recurse Center and return relevant messages. "
            "Pass multiple queries at once to broaden the search; duplicates are removed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "One or more search queries to find relevant Zulip messages.",
                },
            },
            "required": ["queries"],
        },
    },
}


def _validate_structured_answer(content: str) -> dict:
    if not (content or "").strip():
        raise AgentAnswerError("Empty model response")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise AgentAnswerError(f"Invalid JSON: {e}") from e
    for key in ("section_1", "section_2", "section_3"):
        if key not in data:
            raise AgentAnswerError(f"Missing key {key!r}")
        sec = data[key]
        if not isinstance(sec, dict):
            raise AgentAnswerError(f"{key} must be an object")
        for k in ("heading", "text", "citations"):
            if k not in sec:
                raise AgentAnswerError(f"Missing {key}.{k}")
        if not isinstance(sec["citations"], list):
            raise AgentAnswerError(f"{key}.citations must be an array")
        for i, cit in enumerate(sec["citations"]):
            if not isinstance(cit, dict):
                raise AgentAnswerError(f"{key}.citations[{i}] must be an object")
            mid = cit.get("message_id")
            if isinstance(mid, bool) or not isinstance(mid, int):
                raise AgentAnswerError(f"{key}.citations[{i}].message_id must be an integer")
            quote = (cit.get("quote") or "").strip()
            if not quote:
                raise AgentAnswerError(f"{key}.citations[{i}].quote must be non-empty")
    return data


def _call_tool(name: str, arguments: dict) -> str:
    if name == "messages_for_agent":
        result = messages_for_agent(*arguments["queries"])
        return json.dumps(result)
    raise ValueError(f"Unknown tool: {name}")


def run_agent(question: str, max_messages: int = 10, progress_callback=None) -> tuple[list[dict], str]:
    """Run the agentic loop for a user question.

    Returns (message_log, final_answer).
    message_log contains all messages exchanged, including tool calls and results.
    max_messages limits the number of assistant completions from the API before forcing a final answer.
    progress_callback is an optional function(step: str, data: dict) called at key points.
    """
    def _progress(step: str, data: dict):
        if progress_callback:
            progress_callback(step, data)

    client = _openai_client()
    model = _chat_model()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    _progress("searching_zulip", {"query": question})
    bootstrap_id = f"bootstrap_{uuid.uuid4().hex[:16]}"
    bootstrap_results = messages_for_agent(question)
    _progress("search_complete", {"count": len(bootstrap_results)})

    messages.append({
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": bootstrap_id,
            "type": "function",
            "function": {
                "name": "messages_for_agent",
                "arguments": json.dumps({"queries": [question]}),
            },
        }],
    })
    messages.append({
        "role": "tool",
        "tool_call_id": bootstrap_id,
        "content": json.dumps(bootstrap_results),
    })

    agent_message_count = 0

    while True:
        _progress("agent_turn", {"turn": agent_message_count + 1, "max": max_messages})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[TOOL_SCHEMA],
            tool_choice="auto",
            response_format=RESPONSE_SCHEMA,
        )
        logger.info(
            "agent turn %d: finish_reason=%s",
            agent_message_count + 1,
            response.choices[0].finish_reason,
        )

        choice = response.choices[0]
        messages.append(choice.message.model_dump(exclude_unset=False))
        agent_message_count += 1

        if choice.finish_reason == "tool_calls" and agent_message_count < max_messages:
            for tool_call in choice.message.tool_calls or []:
                arguments = json.loads(tool_call.function.arguments)
                queries = arguments.get("queries", [])
                _progress("tool_search", {"queries": queries})
                result = _call_tool(tool_call.function.name, arguments)
                tool_result = json.loads(result)
                _progress("tool_search_complete", {"count": len(tool_result)})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
            continue
        else:
            _progress("finalizing_answer", {})
            final_answer = choice.message.content or ""
            return messages, final_answer

        # if choice.finish_reason == "tool_calls":
        #     for tool_call in choice.message.tool_calls or []:
        #         messages.append({
        #             "role": "tool",
        #             "tool_call_id": tool_call.id,
        #             "content": json.dumps([{
        #                 "error": "search_round_limit",
        #                 "message": "Use prior search results for your JSON answer only.",
        #             }]),
        #         })
        #     continue

        # final_raw = choice.message.content or ""
        # try:
        #     _validate_structured_answer(final_raw)
        #     return messages, final_raw
        # except AgentAnswerError as first_err:
        #     logger.warning("structured answer invalid, attempting repair: %s", first_err.message)

        # messages.append({
        #     "role": "user",
        #     "content": (
        #         "Your previous reply was not valid. Output ONLY one JSON object with keys "
        #         "section_1, section_2, section_3. Each has heading, text, and citations. "
        #         "Each citation has message_id (integer) and quote (short verbatim string). "
        #         "Do not call tools."
        #     ),
        # })

        # repair = client.chat.completions.create(
        #     model=model,
        #     messages=messages,
        #     response_format=RESPONSE_SCHEMA,
        # )
        # choice2 = repair.choices[0]
        # final2 = choice2.message.content or ""
        # try:
        #     _validate_structured_answer(final2)
        # except AgentAnswerError as err:
        #     raise AgentAnswerError(
        #         f"Could not obtain a valid structured answer: {err.message}",
        #     ) from err
        # messages.append(choice2.message.model_dump(exclude_unset=False))
        # return messages, final2
