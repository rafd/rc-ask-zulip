import json
import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

from zulip_search import messages_for_agent

DEFAULT_AI_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_OPENAI_API_KEY = "ollama"
DEFAULT_OPENAI_MODEL = "llama3.1"


def _openai_client() -> OpenAI:
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_AI_BASE_URL).rstrip("/")
    api_key = os.environ.get("OPENAI_API_KEY", DEFAULT_OPENAI_API_KEY)
    return OpenAI(api_key=api_key, base_url=base_url)


def _chat_model() -> str:
    return os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)

SYSTEM_PROMPT = """\
You are an expert research assistant that answers questions about what Recurse Center participants think about topics.

## Search
You have access to a tool that searches Zulip conversations. Use it one or more times to gather relevant messages,
then synthesize a concise summary answering the user's question. Prefer quality over quantity: a few dozen on-topic messages are usually enough.
If a search returns few results, try shorter queries or different phrasings, synonyms, or broader terms.

## Summary Report
In your response, identify multiple different themes (MINIMUM 3 themes) and common ideas in the conversations. 

For each theme, use one object with three fields: "heading", "text", and "message_ids".

"heading" is the title for that theme.
"text" is your executive summary (markdown compatible): be very concise and use bullet points. Keep each bullet short.
"message_ids" lists the Zulip message ids that support the text (use as citations).

Your final response MUST be valid JSON: an object with a "sections" key whose value is an array of theme objects (each theme has all three fields), for example:

{"sections": [
  {"heading": "First theme", "text": "- point one\\n- point two", "message_ids": [123, 456]},
  {"heading": "Second theme", "text": "- another idea", "message_ids": [789]}
]}
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
    """Run the agentic loop for a user question.

    Returns (message_log, final_answer).
    message_log contains all messages exchanged, including tool calls and results.
    max_messages limits the number of assistant+tool messages before forcing a final answer.
    """
    client = _openai_client()
    model = _chat_model()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    agent_message_count = 0

    while True:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[TOOL_SCHEMA],
            tool_choice="auto",
            response_format=RESPONSE_SCHEMA,
        )
        logger.info(
            "agent turn %d: response=%s",
            agent_message_count + 1,
            response,
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
            for tool_call in choice.message.tool_calls:
                arguments = json.loads(tool_call.function.arguments)
                result = _call_tool(tool_call.function.name, arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
        else:
            final_answer = choice.message.content or ""
            return messages, final_answer
