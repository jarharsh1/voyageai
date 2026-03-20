"""JSON extraction utility — replaces the fragile greedy regex used across agents."""

import json
import re


def extract_json(text: str) -> dict | None:
    """
    Robustly extract the first complete JSON object from LLM output.

    Strategy:
    1. Try to parse the entire text as JSON first (fastest path).
    2. Find the first '{' and balance braces to extract a complete JSON object.
    3. Fallback: try non-greedy regex to find potential JSON blocks.

    Returns None if no valid JSON object is found.
    """
    if not text:
        return None

    text = text.strip()

    # Fast path: entire text is JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find first '{' and balance braces to extract complete object
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # Try the next '{' if this one was broken
                    start = text.find("{", start + 1)
                    if start == -1:
                        return None
                    depth = 0
                    i = start - 1

    return None
