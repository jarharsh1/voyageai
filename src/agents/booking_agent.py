"""
Booking Execution Agent
ONLY invoked after explicit user confirmation.
Verifies passenger details, re-checks availability, executes leg by leg.
Stops safely and reports exactly what succeeded/failed.
"""

from src.utils.llm import call_agent
from src.utils.state import TripState, BookingResult, ApprovalStatus

SYSTEM_PROMPT = """
You are the Booking Execution Agent.
You are ONLY invoked after explicit user confirmation.

Before executing:
1. Verify the selected itinerary is complete
2. Verify passenger details are present
3. Verify required constraints (passport for international, etc.)
4. Re-check critical availability if needed
5. Execute leg by leg in the safest order

If any step fails:
- Stop safely
- Report exactly what succeeded and what failed
- Provide recovery options
- Never pretend a booking succeeded if confirmation is missing

IMPORTANT: In this prototype, bookings are SIMULATED. Return a mock booking confirmation.
In production, this agent would call real booking APIs (IRCTC, airline APIs, etc.).
"""


def run(state: TripState) -> TripState:
    # Hard gate — never execute without explicit approval
    if state.approval_status != ApprovalStatus.APPROVED:
        state.add_error("Booking agent invoked without user approval — blocked")
        return state

    if not state.selected_option_id:
        state.add_error("No option selected for booking")
        return state

    # Find the selected option
    selected = next(
        (opt for opt in state.ranked_options if opt.option_id == state.selected_option_id),
        None,
    )
    if not selected:
        state.add_error(f"Selected option {state.selected_option_id} not found in ranked options")
        return state

    state.log("booking_agent", "running", f"Executing booking for {state.selected_option_id}")

    # Build leg summary for the prompt
    legs_text = "\n".join(
        f"Leg {i+1}: [{leg.mode.upper()}] {leg.origin} → {leg.destination} | {leg.carrier} | ₹{leg.fare_inr}"
        for i, leg in enumerate(selected.legs)
    )

    messages = [
        {
            "role": "user",
            "content": f"""
Execute booking for this confirmed itinerary:

PASSENGER COUNT: {state.intent.passenger_count}
JOURNEY: {state.intent.origin} → {state.intent.destination}
DATE: {state.intent.travel_date}

SELECTED ITINERARY ({state.selected_option_id}):
{legs_text}
TOTAL FARE: ₹{selected.total_fare_inr}

This is a PROTOTYPE — simulate the booking and return mock PNR/booking references.

Return JSON:
{{
  "success": true,
  "confirmed_legs": [
    {{
      "leg": "Leg 1",
      "mode": "flight",
      "origin": "<>",
      "destination": "<>",
      "pnr": "<mock PNR>",
      "booking_ref": "<ref>",
      "status": "confirmed"
    }}
  ],
  "failed_legs": [],
  "pnr_numbers": ["<pnr1>", "<pnr2>"],
  "total_charged_inr": 5000,
  "error_message": ""
}}
""",
        }
    ]

    from src.utils.json_utils import extract_json

    result = call_agent(SYSTEM_PROMPT, messages)
    data = extract_json(result["text"])

    booking = BookingResult()
    if data:
        booking.success = bool(data.get("success", False))
        booking.confirmed_legs = data.get("confirmed_legs", [])
        booking.failed_legs = data.get("failed_legs", [])
        booking.pnr_numbers = data.get("pnr_numbers", [])
        booking.error_message = data.get("error_message", "")
    else:
        booking.success = False
        booking.error_message = "No booking response received"

    state.booking_result = booking

    if booking.success:
        state.log(
            "booking_agent",
            "done",
            f"Booking confirmed | PNRs: {', '.join(booking.pnr_numbers)}",
        )
    else:
        state.log("booking_agent", "error", f"Booking failed: {booking.error_message}")

    return state
