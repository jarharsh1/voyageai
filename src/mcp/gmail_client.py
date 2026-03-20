"""
Gmail MCP client.

Wraps calls to the Gmail MCP server via the Claude API `mcp_servers`
parameter. All email operations are performed by Claude using MCP tools.
"""

import os
from typing import Any
import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-4-6"


def _gmail_url() -> str | None:
    return os.getenv("GMAIL_MCP_URL")


def _make_mcp_call(prompt: str) -> str:
    url = _gmail_url()
    if not url:
        return "GMAIL_MCP_URL not configured — email operation skipped"

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
        mcp_servers=[
            {
                "type": "url",
                "url": url,
                "name": "gmail",
            }
        ],
        betas=["mcp-client-2025-11-20"],
    )

    parts = [block.text for block in response.content if hasattr(block, "text")]
    return "\n".join(parts)


def scan_existing_bookings(destination: str, travel_date: str) -> dict[str, Any]:
    """
    Scan Gmail for existing booking confirmation emails related to this trip.
    Returns any prior bookings found so the system can avoid duplicates.
    """
    prompt = f"""
Search my Gmail inbox for any existing travel booking confirmation emails related to:
- Destination: {destination}
- Travel date around: {travel_date}

Look for emails from airlines (IndiGo, Air India, SpiceJet, etc.),
railways (IRCTC), hotels, or travel agents.

Return a JSON object:
{{
  "found": true | false,
  "bookings": [
    {{
      "type": "flight | train | hotel",
      "subject": "<email subject>",
      "from": "<sender>",
      "date": "<email date>",
      "booking_ref": "<PNR or reference number>",
      "summary": "<one line summary>"
    }}
  ],
  "summary": "One sentence summary of what was found"
}}
"""
    raw = _make_mcp_call(prompt)

    from src.utils.json_utils import extract_json
    data = extract_json(raw)
    if data:
        return data

    return {
        "found": False,
        "bookings": [],
        "summary": raw[:300] if raw else "Gmail scan unavailable",
    }


def send_trip_summary(
    origin: str,
    destination: str,
    travel_date: str,
    itinerary_text: str,
    pnr_numbers: list[str],
    total_fare_inr: float,
) -> dict[str, Any]:
    """
    Send a trip confirmation summary email to the user.
    Called only after booking is confirmed and approved.
    """
    pnrs = "\n".join(f"  • {p}" for p in pnr_numbers) if pnr_numbers else "  • N/A"

    prompt = f"""
Send an email to me (myself) with the following trip confirmation details:

Subject: ✈ Trip Confirmed: {origin} → {destination} on {travel_date}

Body:
Your VoyageAI trip has been confirmed!

TRIP DETAILS
━━━━━━━━━━━━
{itinerary_text}

BOOKING REFERENCES
━━━━━━━━━━━━━━━━━
{pnrs}

TOTAL CHARGED
━━━━━━━━━━━━
₹{total_fare_inr:,.0f}

Have a great trip!
— VoyageAI

Return a JSON object:
{{
  "sent": true | false,
  "message_id": "<gmail message id or empty>",
  "message": "<confirmation or error message>"
}}
"""
    raw = _make_mcp_call(prompt)

    from src.utils.json_utils import extract_json
    data = extract_json(raw)
    if data:
        return data

    return {
        "sent": False,
        "message_id": "",
        "message": raw[:300] if raw else "Email send unavailable",
    }
