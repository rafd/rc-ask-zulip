import json
import os

from openai import OpenAI

from zulip_search import messages_for_agent

SYSTEM_PROMPT = """\
You are a helpful assistant that answers questions about what Recurse Center participants think about topics.
You have access to a tool that searches Zulip conversations. Use it one or more times to gather relevant messages,
then synthesize a concise summary answering the user's question.
"""

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "messages_for_agent",
        "description": (
            "Search Zulip conversations at the Recurse Center and return relevant messages. "
            "Call this with different queries to gather information about a topic."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant Zulip messages.",
                },
            },
            "required": ["query"],
        },
    },
}


def _call_tool(name: str, arguments: dict) -> str:
    if name == "messages_for_agent":
        result = messages_for_agent(arguments["query"])
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
            final_answer = choice.message.content
            return messages, final_answer
