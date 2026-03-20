"""
Calendar Agent
Checks Google Calendar for conflicts on the requested travel dates.
Runs early in the pipeline — before route planning — so conflicts can
influence date suggestions.

On booking confirmation it also creates the trip event in Google Calendar.
"""

from src.utils.state import TripState


def run(state: TripState) -> TripState:
    state.log("calendar_agent", "running", "Checking Google Calendar for conflicts")

    from src.mcp.gcal_client import check_conflicts

    travel_date = state.intent.travel_date
    return_date = state.intent.return_date

    if not travel_date:
        state.log("calendar_agent", "done", "No travel date set — skipping conflict check")
        return state

    result = check_conflicts(travel_date, return_date)

    # Store raw conflicts in state
    state.calendar_conflicts = result.get("conflicts", [])

    blocking = [c for c in state.calendar_conflicts if c.get("severity") == "blocking"]

    if blocking:
        conflict_titles = ", ".join(c.get("title", "event") for c in blocking)
        state.log(
            "calendar_agent",
            "done",
            f"⚠ {len(blocking)} blocking conflict(s): {conflict_titles}",
        )
        # Surface as a soft warning — do not block planning
        state.add_error(
            f"Calendar conflict on {travel_date}: {conflict_titles}. "
            "Consider rescheduling or proceed knowing you have commitments."
        )
    else:
        summary = result.get("summary", "Calendar is clear")
        state.log("calendar_agent", "done", f"✓ {summary}")

    return state


def create_event_after_booking(state: TripState) -> TripState:
    """
    Called after a successful booking to add the trip to Google Calendar.
    Only runs if booking_result.success is True.
    """
    if not state.booking_result or not state.booking_result.success:
        return state

    state.log("calendar_agent", "running", "Creating trip event in Google Calendar")

    from src.mcp.gcal_client import create_trip_event

    selected = next(
        (opt for opt in state.ranked_options if opt.option_id == state.selected_option_id),
        None,
    )
    summary_text = state.summary or f"Trip from {state.intent.origin} to {state.intent.destination}"

    result = create_trip_event(
        origin=state.intent.origin,
        destination=state.intent.destination,
        travel_date=state.intent.travel_date,
        return_date=state.intent.return_date,
        summary_text=summary_text,
        pnr_numbers=state.booking_result.pnr_numbers,
    )

    if result.get("created"):
        state.log(
            "calendar_agent",
            "done",
            f"✓ Calendar event created: {result.get('event_link') or result.get('event_id', 'OK')}",
        )
    else:
        state.log(
            "calendar_agent",
            "done",
            f"Calendar event skipped: {result.get('message', 'unknown')}",
        )

    return state
