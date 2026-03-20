"""
Google Calendar MCP client.

Wraps calls to the Google Calendar MCP server via the Claude API
`mcp_servers` parameter. All calendar operations are performed by
Claude using the MCP tools — we never call the Calendar API directly.
"""

import os
from typing import Any
import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-4-6"


def _gcal_url() -> str | None:
    return os.getenv("GCAL_MCP_URL")


def _make_mcp_call(prompt: str) -> str:
    """
    Send a prompt to Claude with the Google Calendar MCP server attached.
    Returns the text response.
    """
    url = _gcal_url()
    if not url:
        return "GCAL_MCP_URL not configured — calendar check skipped"

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
        mcp_servers=[
            {
                "type": "url",
                "url": url,
                "name": "google-calendar",
            }
        ],
        betas=["mcp-client-2025-11-20"],
    )

    parts = [block.text for block in response.content if hasattr(block, "text")]
    return "\n".join(parts)


def check_conflicts(travel_date: str, return_date: str = "") -> dict[str, Any]:
    """
    Ask the Calendar MCP whether the user has conflicts on the travel dates.
    Returns a dict with keys: has_conflicts (bool), conflicts (list), summary (str).
    """
    date_range = travel_date
    if return_date:
        date_range = f"{travel_date} to {return_date}"

    prompt = f"""
Check my Google Calendar for any existing events or conflicts on {date_range}.

Return a JSON object:
{{
  "has_conflicts": true | false,
  "conflicts": [
    {{
      "title": "<event title>",
      "date": "<date>",
      "time": "<time range>",
      "severity": "blocking | informational"
    }}
  ],
  "free_slots": ["<time ranges that are free for travel>"],
  "summary": "One sentence summary of availability"
}}
"""
    raw = _make_mcp_call(prompt)

    from src.utils.json_utils import extract_json
    data = extract_json(raw)
    if data:
        return data

    # Graceful fallback if MCP returns non-JSON
    return {
        "has_conflicts": False,
        "conflicts": [],
        "free_slots": [],
        "summary": raw[:300] if raw else "Calendar check unavailable",
    }


def create_trip_event(
    origin: str,
    destination: str,
    travel_date: str,
    return_date: str,
    summary_text: str,
    pnr_numbers: list[str],
) -> dict[str, Any]:
    """
    Create a calendar event for the confirmed trip.
    Called only after the user has approved and booking is confirmed.
    """
    pnrs = ", ".join(pnr_numbers) if pnr_numbers else "N/A"
    end_date = return_date if return_date else travel_date

    prompt = f"""
Create a Google Calendar event for this confirmed trip:

Title: Trip: {origin} → {destination}
Start date: {travel_date}
End date: {end_date}
Description:
  {summary_text}
  PNR / Booking refs: {pnrs}

Mark it as "Out of office" if that status is available.
Return a JSON object:
{{
  "created": true | false,
  "event_id": "<calendar event id or empty>",
  "event_link": "<link or empty>",
  "message": "<confirmation or error message>"
}}
"""
    raw = _make_mcp_call(prompt)

    from src.utils.json_utils import extract_json
    data = extract_json(raw)
    if data:
        return data

    return {
        "created": False,
        "event_id": "",
        "event_link": "",
        "message": raw[:300] if raw else "Calendar event creation unavailable",
    }
