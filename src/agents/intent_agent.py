"""
Intent Extraction Agent
Extracts and normalises: origin, destination, dates, trip type, priorities.
Returns structured output only. Does not plan routes.
"""

import json
import re
from src.utils.llm import call_agent
from src.utils.state import TripState, Intent, TripType

SYSTEM_PROMPT = """
You are the Intent Extraction Agent.

Extract and normalize:
- origin (default to Delhi if not stated)
- destination
- travel_date (ISO format YYYY-MM-DD if possible, else natural language)
- return_date (empty string if one-way)
- is_round_trip (boolean)
- is_international (boolean — true if destination is outside India)
- passenger_count (integer, default 1)
- priorities (list of strings from: ["cheap", "fast", "comfortable", "fewer_transfers", "direct"])

Rules:
- Do not plan routes.
- Do not assume missing fields unless clearly inferable from context.
- If destination is ambiguous, list possible interpretations in "destination_ambiguities".
- Return ONLY valid JSON, no extra commentary.
"""


def run(state: TripState) -> TripState:
    state.log("intent_agent", "running", "Extracting and normalising travel intent")

    messages = [
        {
            "role": "user",
            "content": f"""
Extract travel intent from this request and return valid JSON:

REQUEST: {state.user_request}

Return exactly this JSON structure:
{{
  "origin": "Delhi",
  "destination": "<extracted destination>",
  "travel_date": "<YYYY-MM-DD or natural language or empty>",
  "return_date": "<YYYY-MM-DD or empty if one-way>",
  "is_round_trip": false,
  "is_international": false,
  "passenger_count": 1,
  "priorities": [],
  "destination_ambiguities": [],
  "missing_critical": []
}}
""",
        }
    ]

    result = call_agent(SYSTEM_PROMPT, messages)

    text = result["text"]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            intent = state.intent
            intent.origin = data.get("origin", "Delhi")
            intent.destination = data.get("destination", "")
            intent.travel_date = data.get("travel_date", "")
            intent.return_date = data.get("return_date", "")
            intent.is_round_trip = bool(data.get("is_round_trip", False))
            intent.is_international = bool(data.get("is_international", False))
            intent.passenger_count = int(data.get("passenger_count", 1))
            intent.priorities = data.get("priorities", [])
            intent.ambiguities = data.get("destination_ambiguities", []) + data.get("missing_critical", [])

            state.log(
                "intent_agent",
                "done",
                f"{intent.origin} → {intent.destination} | {intent.travel_date} | {'International' if intent.is_international else 'Domestic'}",
            )
        except (json.JSONDecodeError, ValueError) as e:
            state.add_error(f"Intent extraction parse error: {e}")
    else:
        state.add_error("Intent agent returned no parseable JSON")

    return state
