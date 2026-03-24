import json
import os

from openai import OpenAI

from zulip_search import messages_for_agent

SYSTEM_PROMPT = """\
You are a helpful assistant that answers questions about what Recurse Center participants think about topics.
You have access to a tool that searches Zulip conversations. Use it one or more times to gather relevant messages,
then synthesize a concise summary answering the user's question. If you don't get a lot of messages, use shorter queries.

Your final response MUST be valid JSON: an object with a "sections" key containing an array of section objects, each one of:
  {"text": "narrative text here"}
  {"message_ids": [123, 456, 789]}

Use "text" sections for your own narrative and "message_ids" sections to cite the specific Zulip messages
that support the adjacent text. Interleave them so citations appear next to the relevant passage.
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
                        "anyOf": [
                            {
                                "type": "object",
                                "properties": {"text": {"type": "string"}},
                                "required": ["text"],
                                "additionalProperties": False,
                            },
                            {
                                "type": "object",
                                "properties": {
                                    "message_ids": {
                                        "type": "array",
                                        "items": {"type": "integer"},
                                    }
                                },
                                "required": ["message_ids"],
                                "additionalProperties": False,
                            },
                        ]
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
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    agent_message_count = 0

    while True:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=[TOOL_SCHEMA],
            tool_choice="auto",
            response_format=RESPONSE_SCHEMA,
        )
        choice = response.choices[0]
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
