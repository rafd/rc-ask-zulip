import json
import logging
import os
import uuid

from llm_client import build_openai_client
from zulip_search import messages_for_agent

logger = logging.getLogger(__name__)


class AgentAnswerError(Exception):
    """Raised when the model returns an invalid structured answer."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _openai_client():
    """Construct the OpenAI-compatible client.

    Raises ExternalLLMNotAllowedError if OPENAI_BASE_URL is set to a blocked
    provider (OpenAI/ChatGPT, Anthropic/Claude, Google Gemini).
    """
    return build_openai_client()


def _chat_model() -> str:
    local_ollama_model = "llama3.1"
    return os.environ.get("OPENAI_MODEL", local_ollama_model)


SYSTEM_PROMPT = """\
You are an expert research assistant that answers questions about what Recurse Center participants think about topics.

## Search
You have access to a tool that searches Zulip conversations. Use it one or more times to gather relevant messages,
then synthesize a concise summary answering the user's question. Prefer quality over quantity: a few dozen on-topic messages are usually enough.
If a search returns few results, try shorter queries or different phrasings, synonyms, or broader terms.

## Answer format (required)
Respond with ONLY a JSON object (no markdown fences, no commentary) with this shape:
{"sections": [{"heading": "...", "text": "- bullet", "message_ids": [123]}]}

For each theme, use one object with three fields: "heading", "text", and "message_ids".
"text" must be concise bullet lines.
"message_ids" must contain only ids from search/tool results.
"""


RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "answer_sections",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "text": {"type": "string"},
                            "message_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                        },
                        "required": ["heading", "text", "message_ids"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["sections"],
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


def _call_tool(name: str, arguments: dict) -> str:
    if name == "messages_for_agent":
        result = messages_for_agent(*arguments["queries"])
        return json.dumps(result)
    raise ValueError(f"Unknown tool: {name}")


def run_agent(question: str, max_messages: int = 10) -> tuple[list[dict], str]:
    client = _openai_client()
    model = _chat_model()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    bootstrap_id = f"bootstrap_{uuid.uuid4().hex[:16]}"
    bootstrap_results = messages_for_agent(question)
    messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": bootstrap_id,
                    "type": "function",
                    "function": {
                        "name": "messages_for_agent",
                        "arguments": json.dumps({"queries": [question]}),
                    },
                }
            ],
        }
    )
    messages.append(
        {
            "role": "tool",
            "tool_call_id": bootstrap_id,
            "content": json.dumps(bootstrap_results),
        }
    )

    agent_message_count = 0
    while True:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[TOOL_SCHEMA],
            tool_choice="auto",
            response_format=RESPONSE_SCHEMA,
        )

        choice = response.choices[0]
        n_tools = len(choice.message.tool_calls or [])
        logger.info(
            "agent turn %d: finish_reason=%s tool_calls=%d",
            agent_message_count + 1,
            choice.finish_reason,
            n_tools,
        )
        messages.append(choice.message.model_dump(exclude_unset=False))
        agent_message_count += 1

        if choice.finish_reason == "tool_calls" and agent_message_count < max_messages:
            for tool_call in choice.message.tool_calls or []:
                arguments = json.loads(tool_call.function.arguments)
                result = _call_tool(tool_call.function.name, arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )
            continue

        final_answer = choice.message.content or ""
        return messages, final_answer
