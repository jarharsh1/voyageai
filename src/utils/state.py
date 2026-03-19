"""Trip state management — shared state passed through the LangGraph graph."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal
from enum import Enum


class TripType(str, Enum):
    DIRECT_DOMESTIC = "direct_domestic"
    DIRECT_INTERNATIONAL = "direct_international"
    INDIRECT_MULTIMODAL = "indirect_multimodal"
    UNKNOWN = "unknown"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


@dataclass
class Intent:
    origin: str = "Delhi"
    destination: str = ""
    travel_date: str = ""
    return_date: str = ""          # empty = one-way
    passenger_count: int = 1
    trip_type: TripType = TripType.UNKNOWN
    priorities: list[str] = field(default_factory=list)   # ["cheap","fast",...]
    is_round_trip: bool = False
    is_international: bool = False
    ambiguities: list[str] = field(default_factory=list)  # unresolved fields


@dataclass
class Leg:
    mode: str = ""          # "flight" | "train" | "bus" | "taxi"
    origin: str = ""
    destination: str = ""
    departure_time: str = ""
    arrival_time: str = ""
    duration_minutes: int = 0
    carrier: str = ""
    fare_inr: float = 0.0
    booking_class: str = ""
    notes: str = ""


@dataclass
class RouteOption:
    option_id: str = ""
    legs: list[Leg] = field(default_factory=list)
    total_duration_minutes: int = 0
    total_fare_inr: float = 0.0
    transfer_count: int = 0
    convenience_score: float = 0.0   # 0–10
    risk_notes: list[str] = field(default_factory=list)
    rank: int = 0
    recommended: bool = False


@dataclass
class BookingResult:
    success: bool = False
    confirmed_legs: list[dict] = field(default_factory=list)
    failed_legs: list[dict] = field(default_factory=list)
    pnr_numbers: list[str] = field(default_factory=list)
    error_message: str = ""


@dataclass
class AgentLog:
    agent_name: str = ""
    status: Literal["running", "done", "error"] = "running"
    message: str = ""


@dataclass
class TripState:
    """Shared state passed between all LangGraph nodes."""

    # Raw user input
    user_request: str = ""

    # Extracted intent
    intent: Intent = field(default_factory=Intent)

    # Route candidates from Route Planning agent
    route_options: list[RouteOption] = field(default_factory=list)

    # Raw search results from specialist agents
    flight_results: list[dict] = field(default_factory=list)
    train_results: list[dict] = field(default_factory=list)
    ground_transport_results: list[dict] = field(default_factory=list)

    # Calendar / email context (from MCP agents)
    calendar_conflicts: list[dict] = field(default_factory=list)
    existing_bookings: list[dict] = field(default_factory=list)

    # Ranked & recommended options (from Decision agent)
    ranked_options: list[RouteOption] = field(default_factory=list)
    recommended_option_id: str = ""

    # Human-in-the-loop
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    selected_option_id: str = ""
    user_feedback: str = ""

    # Booking result (only set after approval + execution)
    booking_result: BookingResult | None = None

    # Errors and agent activity log
    errors: list[str] = field(default_factory=list)
    agent_log: list[AgentLog] = field(default_factory=list)

    # Final human-readable summary for display
    summary: str = ""

    def log(self, agent: str, status: str, message: str) -> None:
        self.agent_log.append(AgentLog(agent_name=agent, status=status, message=message))

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.log("system", "error", message)

    def to_dict(self) -> dict[str, Any]:
        """Serialise state for API responses and frontend consumption."""
        return {
            "user_request": self.user_request,
            "intent": {
                "origin": self.intent.origin,
                "destination": self.intent.destination,
                "travel_date": self.intent.travel_date,
                "return_date": self.intent.return_date,
                "passenger_count": self.intent.passenger_count,
                "trip_type": self.intent.trip_type.value,
                "priorities": self.intent.priorities,
                "is_round_trip": self.intent.is_round_trip,
                "is_international": self.intent.is_international,
                "ambiguities": self.intent.ambiguities,
            },
            "route_options": [
                {
                    "option_id": opt.option_id,
                    "legs": [
                        {
                            "mode": leg.mode,
                            "origin": leg.origin,
                            "destination": leg.destination,
                            "departure_time": leg.departure_time,
                            "arrival_time": leg.arrival_time,
                            "duration_minutes": leg.duration_minutes,
                            "carrier": leg.carrier,
                            "fare_inr": leg.fare_inr,
                            "booking_class": leg.booking_class,
                            "notes": leg.notes,
                        }
                        for leg in opt.legs
                    ],
                    "total_duration_minutes": opt.total_duration_minutes,
                    "total_fare_inr": opt.total_fare_inr,
                    "transfer_count": opt.transfer_count,
                    "convenience_score": opt.convenience_score,
                    "risk_notes": opt.risk_notes,
                    "rank": opt.rank,
                    "recommended": opt.recommended,
                }
                # After decision agent runs, ranked_options is populated; fall back to route_options
                for opt in (self.ranked_options if self.ranked_options else self.route_options)
            ],
            "recommended_option_id": self.recommended_option_id,
            "approval_status": self.approval_status.value,
            "selected_option_id": self.selected_option_id,
            "booking_result": (
                {
                    "success": self.booking_result.success,
                    "confirmed_legs": self.booking_result.confirmed_legs,
                    "failed_legs": self.booking_result.failed_legs,
                    "pnr_numbers": self.booking_result.pnr_numbers,
                    "error_message": self.booking_result.error_message,
                }
                if self.booking_result
                else None
            ),
            "errors": self.errors,
            "agent_log": [
                {"agent": log.agent_name, "status": log.status, "message": log.message}
                for log in self.agent_log
            ],
            "summary": self.summary,
        }
