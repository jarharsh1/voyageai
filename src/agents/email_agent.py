"""
Email Agent
Uses Gmail MCP for two tasks:

1. Pre-planning scan — checks inbox for existing booking confirmations
   for this destination/date to avoid duplicate bookings.

2. Post-booking summary — sends a formatted trip confirmation email
   to the user after approval and successful booking.
"""

from src.utils.state import TripState


def scan_inbox(state: TripState) -> TripState:
    """
    Scan Gmail for existing confirmations before planning starts.
    Runs in parallel with the calendar agent.
    """
    state.log("email_agent", "running", "Scanning Gmail for existing booking confirmations")

    from src.mcp.gmail_client import scan_existing_bookings

    destination = state.intent.destination
    travel_date = state.intent.travel_date

    if not destination:
        state.log("email_agent", "done", "No destination set — skipping inbox scan")
        return state

    result = scan_existing_bookings(destination, travel_date)

    state.existing_bookings = result.get("bookings", [])

    if result.get("found") and state.existing_bookings:
        refs = ", ".join(
            b.get("booking_ref", "?") for b in state.existing_bookings if b.get("booking_ref")
        )
        state.log(
            "email_agent",
            "done",
            f"⚠ Found {len(state.existing_bookings)} existing booking(s): {refs}",
        )
        state.add_error(
            f"Found existing booking confirmation(s) for {destination} in Gmail "
            f"(refs: {refs}). Verify this is not a duplicate booking."
        )
    else:
        summary = result.get("summary", "No existing bookings found")
        state.log("email_agent", "done", f"✓ {summary}")

    return state


def send_confirmation(state: TripState) -> TripState:
    """
    Send a trip summary email after successful booking.
    Only runs if booking_result.success is True.
    """
    if not state.booking_result or not state.booking_result.success:
        return state

    state.log("email_agent", "running", "Sending trip confirmation email via Gmail")

    from src.mcp.gmail_client import send_trip_summary

    selected = next(
        (opt for opt in state.ranked_options if opt.option_id == state.selected_option_id),
        None,
    )

    # Build a plain-text itinerary for the email body
    if selected:
        leg_lines = []
        for i, leg in enumerate(selected.legs, 1):
            leg_lines.append(
                f"Leg {i}: [{leg.mode.upper()}] {leg.origin} → {leg.destination} "
                f"| {leg.departure_time}–{leg.arrival_time} | {leg.carrier} | ₹{leg.fare_inr:,.0f}"
            )
        itinerary_text = "\n".join(leg_lines)
        total_fare = selected.total_fare_inr
    else:
        itinerary_text = state.summary or "Details unavailable"
        total_fare = 0.0

    result = send_trip_summary(
        origin=state.intent.origin,
        destination=state.intent.destination,
        travel_date=state.intent.travel_date,
        itinerary_text=itinerary_text,
        pnr_numbers=state.booking_result.pnr_numbers,
        total_fare_inr=total_fare,
    )

    if result.get("sent"):
        state.log("email_agent", "done", "✓ Trip confirmation email sent")
    else:
        state.log(
            "email_agent",
            "done",
            f"Email skipped: {result.get('message', 'unknown')}",
        )

    return state
