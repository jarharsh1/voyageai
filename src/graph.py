"""
LangGraph orchestration graph for VoyageAI.

Planning flow:
  orchestrator → intent
                    ├─ calendar_check  (parallel)
                    └─ email_scan      (parallel)
                    ↓  (fan-in)
               route_agent → search_agent → decision_agent
                                                  ↓
                                         [APPROVAL GATE]

Booking flow (separate graph, runs only after approval):
  booking → calendar_event → email_confirmation → END

Workflow types:
- Sequential: orchestrator → intent → route → decision
- Parallel: calendar_check + email_scan run concurrently after intent
- Conditional: booking only if approval_status == APPROVED
- Post-booking: calendar event + email confirmation after successful booking
"""

from __future__ import annotations
from typing import Literal

from langgraph.graph import StateGraph, END

from src.utils.state import TripState, ApprovalStatus
from src.agents import (
    orchestrator,
    intent_agent,
    route_agent,
    search_agent,
    decision_agent,
    booking_agent,
    calendar_agent,
    email_agent,
)


# ─── Node wrappers ─────────────────────────────────────────────────────────────

def _node_orchestrator(state: dict) -> dict:
    trip = _from_dict(state)
    trip = orchestrator.run(trip)
    return trip.to_dict()


def _node_intent(state: dict) -> dict:
    trip = _from_dict(state)
    trip = intent_agent.run(trip)
    return trip.to_dict()


def _node_calendar_check(state: dict) -> dict:
    trip = _from_dict(state)
    trip = calendar_agent.run(trip)
    return trip.to_dict()


def _node_email_scan(state: dict) -> dict:
    trip = _from_dict(state)
    trip = email_agent.scan_inbox(trip)
    return trip.to_dict()


def _node_route(state: dict) -> dict:
    trip = _from_dict(state)
    trip = route_agent.run(trip)
    return trip.to_dict()


def _node_search(state: dict) -> dict:
    trip = _from_dict(state)
    trip = search_agent.run(trip)
    return trip.to_dict()


def _node_decision(state: dict) -> dict:
    trip = _from_dict(state)
    trip = decision_agent.run(trip)
    return trip.to_dict()


def _node_booking(state: dict) -> dict:
    trip = _from_dict(state)
    trip = booking_agent.run(trip)
    return trip.to_dict()


def _node_calendar_event(state: dict) -> dict:
    trip = _from_dict(state)
    trip = calendar_agent.create_event_after_booking(trip)
    return trip.to_dict()


def _node_email_confirmation(state: dict) -> dict:
    trip = _from_dict(state)
    trip = email_agent.send_confirmation(trip)
    return trip.to_dict()


# ─── Conditional edges ─────────────────────────────────────────────────────────

def _route_after_decision(state: dict) -> Literal["booking", "end"]:
    approval = state.get("approval_status", "pending")
    if approval == ApprovalStatus.APPROVED.value:
        return "booking"
    return "end"


# ─── State reconstruction helper ───────────────────────────────────────────────

def _from_dict(d: dict) -> TripState:
    """Reconstruct a TripState from a serialised dict (LangGraph state)."""
    from src.utils.state import Intent, TripType, ApprovalStatus, AgentLog, RouteOption, Leg, BookingResult

    trip = TripState()
    trip.user_request = d.get("user_request", "")
    trip.summary = d.get("summary", "")
    trip.errors = d.get("errors", [])
    trip.flight_results = d.get("flight_results", [])
    trip.train_results = d.get("train_results", [])
    trip.ground_transport_results = d.get("ground_transport_results", [])
    trip.calendar_conflicts = d.get("calendar_conflicts", [])
    trip.existing_bookings = d.get("existing_bookings", [])
    trip.recommended_option_id = d.get("recommended_option_id", "")
    trip.selected_option_id = d.get("selected_option_id", "")
    trip.user_feedback = d.get("user_feedback", "")

    # Intent
    intent_data = d.get("intent", {})
    trip_type_val = intent_data.get("trip_type", "unknown")
    try:
        trip_type = TripType(trip_type_val)
    except ValueError:
        trip_type = TripType.UNKNOWN

    trip.intent = Intent(
        origin=intent_data.get("origin", "Delhi"),
        destination=intent_data.get("destination", ""),
        travel_date=intent_data.get("travel_date", ""),
        return_date=intent_data.get("return_date", ""),
        passenger_count=int(intent_data.get("passenger_count", 1)),
        trip_type=trip_type,
        priorities=intent_data.get("priorities", []),
        is_round_trip=bool(intent_data.get("is_round_trip", False)),
        is_international=bool(intent_data.get("is_international", False)),
        ambiguities=intent_data.get("ambiguities", []),
    )

    # Approval
    approval_val = d.get("approval_status", "pending")
    try:
        trip.approval_status = ApprovalStatus(approval_val)
    except ValueError:
        trip.approval_status = ApprovalStatus.PENDING

    # Route / ranked options
    def _parse_options(opts_data: list) -> list[RouteOption]:
        opts = []
        for opt_data in opts_data:
            legs = []
            for leg_data in opt_data.get("legs", []):
                legs.append(Leg(
                    mode=leg_data.get("mode", ""),
                    origin=leg_data.get("origin", ""),
                    destination=leg_data.get("destination", ""),
                    departure_time=leg_data.get("departure_time", ""),
                    arrival_time=leg_data.get("arrival_time", ""),
                    duration_minutes=int(leg_data.get("duration_minutes", 0)),
                    carrier=leg_data.get("carrier", ""),
                    fare_inr=float(leg_data.get("fare_inr", 0)),
                    booking_class=leg_data.get("booking_class", ""),
                    notes=leg_data.get("notes", ""),
                ))
            opts.append(RouteOption(
                option_id=opt_data.get("option_id", ""),
                legs=legs,
                total_duration_minutes=int(opt_data.get("total_duration_minutes", 0)),
                total_fare_inr=float(opt_data.get("total_fare_inr", 0)),
                transfer_count=int(opt_data.get("transfer_count", 0)),
                convenience_score=float(opt_data.get("convenience_score", 0)),
                risk_notes=opt_data.get("risk_notes", []),
                rank=int(opt_data.get("rank", 0)),
                recommended=bool(opt_data.get("recommended", False)),
            ))
        return opts

    # to_dict() emits ranked_options (falling back to route_options) under "route_options".
    # On round-trip both fields restore from the same key.
    parsed = _parse_options(d.get("route_options", []))
    trip.route_options = parsed
    trip.ranked_options = parsed

    # Agent log
    trip.agent_log = [
        AgentLog(agent_name=log.get("agent", ""), status=log.get("status", ""), message=log.get("message", ""))
        for log in d.get("agent_log", [])
    ]

    # Booking result
    br_data = d.get("booking_result")
    if br_data:
        trip.booking_result = BookingResult(
            success=bool(br_data.get("success", False)),
            confirmed_legs=br_data.get("confirmed_legs", []),
            failed_legs=br_data.get("failed_legs", []),
            pnr_numbers=br_data.get("pnr_numbers", []),
            error_message=br_data.get("error_message", ""),
        )

    return trip


# ─── Planning graph ─────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Planning pipeline graph.

    orchestrator → intent ──┬── calendar_check ─┐
                            └── email_scan      ─┤ (fan-in via route)
                                                  ↓
                                         route → search → decision → END
                                                              (approval gate)
    """
    graph = StateGraph(dict)

    graph.add_node("orchestrator", _node_orchestrator)
    graph.add_node("intent", _node_intent)
    graph.add_node("calendar_check", _node_calendar_check)
    graph.add_node("email_scan", _node_email_scan)
    graph.add_node("route", _node_route)
    graph.add_node("search", _node_search)
    graph.add_node("decision", _node_decision)

    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", "intent")

    # Fan-out: calendar + email run in parallel after intent
    graph.add_edge("intent", "calendar_check")
    graph.add_edge("intent", "email_scan")

    # Fan-in: both must complete before route planning
    graph.add_edge("calendar_check", "route")
    graph.add_edge("email_scan", "route")

    graph.add_edge("route", "search")
    graph.add_edge("search", "decision")
    graph.add_edge("decision", END)

    return graph.compile()


# ─── Booking graph ──────────────────────────────────────────────────────────────

def build_booking_graph() -> StateGraph:
    """
    Post-approval booking pipeline.
    booking → calendar_event → email_confirmation → END
    """
    graph = StateGraph(dict)

    graph.add_node("booking", _node_booking)
    graph.add_node("calendar_event", _node_calendar_event)
    graph.add_node("email_confirmation", _node_email_confirmation)

    graph.set_entry_point("booking")
    graph.add_edge("booking", "calendar_event")
    graph.add_edge("calendar_event", "email_confirmation")
    graph.add_edge("email_confirmation", END)

    return graph.compile()


# ─── Public API ─────────────────────────────────────────────────────────────────

def run_planning_pipeline(user_request: str) -> dict:
    """
    Run the full planning pipeline.
    Returns state dict with ranked options for human review.
    Does NOT book anything.
    """
    graph = build_graph()
    initial_state = TripState(user_request=user_request).to_dict()
    return graph.invoke(initial_state)


def run_booking_pipeline(state_dict: dict, selected_option_id: str) -> dict:
    """
    Run booking after user approval.
    On success also creates a calendar event and sends a confirmation email.
    """
    state_dict = dict(state_dict)  # shallow copy — don't mutate caller's state
    state_dict["approval_status"] = ApprovalStatus.APPROVED.value
    state_dict["selected_option_id"] = selected_option_id

    return build_booking_graph().invoke(state_dict)
