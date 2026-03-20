"""Claude API client helper — streaming, adaptive thinking, tool use."""

import os
from typing import Any, Generator
import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-4-6"
_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY is not set")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def call_agent(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 4096,
    use_thinking: bool = False,
) -> dict:
    """
    Single Claude API call. Returns the full response message.
    Uses adaptive thinking when requested.
    """
    client = get_client()
    kwargs: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
    if use_thinking:
        kwargs["thinking"] = {"type": "adaptive"}

    response = client.messages.create(**kwargs)
    return _parse_response(response)


def stream_agent(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 8192,
) -> Generator[str, None, dict]:
    """
    Streaming Claude API call. Yields text deltas, returns final message dict.
    """
    client = get_client()
    kwargs: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    with client.messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            yield text
        final = stream.get_final_message()

    return _parse_response(final)


def run_tool_loop(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    tool_executor: Any,
    max_tokens: int = 4096,
    max_iterations: int = 10,
) -> dict:
    """
    Full agentic tool-use loop. Calls Claude, executes tools, feeds results back.
    tool_executor: callable(tool_name, tool_input) -> str
    Returns the final parsed response.
    """
    client = get_client()
    history = list(messages)

    for _ in range(max_iterations):
        response = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=history,
            tools=tools,
        )

        if response.stop_reason == "end_turn":
            return _parse_response(response)

        if response.stop_reason == "tool_use":
            # Append assistant turn
            history.append({"role": "assistant", "content": response.content})

            # Execute all tool calls and collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = tool_executor(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })

            history.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason
        return _parse_response(response)

    # Exhausted iterations — return last response
    return _parse_response(response)


def _parse_response(response: anthropic.types.Message) -> dict:
    """Extract text and metadata from a Claude response."""
    text_parts = []
    tool_calls = []

    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append({
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
        elif block.type == "thinking":
            pass  # Internal reasoning — not surfaced in output

    return {
        "text": "\n".join(text_parts),
        "tool_calls": tool_calls,
        "stop_reason": response.stop_reason,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }
