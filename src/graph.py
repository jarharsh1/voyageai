"""
LangGraph orchestration graph for VoyageAI.

Flow:
  orchestrator → intent_agent → route_agent → search_agent
                                                   ↓
                                            decision_agent
                                                   ↓
                                          [APPROVAL GATE]
                                                   ↓
                                           booking_agent (on approval)

Workflow types:
- Sequential: orchestrator → intent → route → decision → approval → booking
- Parallel-ready: search_agent runs flight+train+ground (can be parallelised)
- Conditional: booking only if approval_status == APPROVED
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
)


# ─── Node wrappers ────────────────────────────────────────────────────────────
# LangGraph nodes receive and return state dicts; we wrap our dataclass agents.

def _node_orchestrator(state: dict) -> dict:
    trip = _from_dict(state)
    trip = orchestrator.run(trip)
    return trip.to_dict()


def _node_intent(state: dict) -> dict:
    trip = _from_dict(state)
    trip = intent_agent.run(trip)
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


# ─── Conditional edge: route after decision ───────────────────────────────────

def _route_after_decision(state: dict) -> Literal["booking", "end"]:
    approval = state.get("approval_status", "pending")
    if approval == ApprovalStatus.APPROVED.value:
        return "booking"
    return "end"


# ─── State reconstruction helper ──────────────────────────────────────────────

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
    trip.intent = Intent(
        origin=intent_data.get("origin", "Delhi"),
        destination=intent_data.get("destination", ""),
        travel_date=intent_data.get("travel_date", ""),
        return_date=intent_data.get("return_date", ""),
        passenger_count=int(intent_data.get("passenger_count", 1)),
        trip_type=TripType(intent_data.get("trip_type", "unknown")) if intent_data.get("trip_type") in TripType._value2member_map_ else TripType.UNKNOWN,
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

    # route_options holds the raw planning candidates; ranked_options holds the
    # post-decision ranked list.  to_dict() emits both under "route_options" (the
    # display list) by merging, so on round-trip both fields restore from the same key.
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


# ─── Build the graph ──────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(dict)

    # Register nodes
    graph.add_node("orchestrator", _node_orchestrator)
    graph.add_node("intent", _node_intent)
    graph.add_node("route", _node_route)
    graph.add_node("search", _node_search)
    graph.add_node("decision", _node_decision)
    graph.add_node("booking", _node_booking)

    # Sequential edges
    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", "intent")
    graph.add_edge("intent", "route")
    graph.add_edge("route", "search")
    graph.add_edge("search", "decision")

    # Conditional: only book if approved
    graph.add_conditional_edges(
        "decision",
        _route_after_decision,
        {"booking": "booking", "end": END},
    )
    graph.add_edge("booking", END)

    return graph.compile()


# ─── Public API ───────────────────────────────────────────────────────────────

def run_planning_pipeline(user_request: str) -> dict:
    """
    Run the full planning pipeline (orchestrator → decision).
    Returns state dict with ranked options for human review.
    Does NOT book anything.
    """
    graph = build_graph()
    initial_state = TripState(user_request=user_request).to_dict()
    final_state = graph.invoke(initial_state)
    return final_state


def run_booking_pipeline(state_dict: dict, selected_option_id: str) -> dict:
    """
    Run booking after user approval.
    Uses a dedicated single-node graph so we never re-run the planning pipeline.
    """
    state_dict = dict(state_dict)  # shallow copy — don't mutate the caller's state
    state_dict["approval_status"] = ApprovalStatus.APPROVED.value
    state_dict["selected_option_id"] = selected_option_id

    # Dedicated booking-only graph — starts and ends at the booking node
    booking_graph = StateGraph(dict)
    booking_graph.add_node("booking", _node_booking)
    booking_graph.set_entry_point("booking")
    booking_graph.add_edge("booking", END)
    compiled = booking_graph.compile()

    return compiled.invoke(state_dict)
