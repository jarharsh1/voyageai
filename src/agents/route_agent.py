"""
Route Planning Agent
Decides if the journey is direct or indirect. Builds realistic end-to-end route candidates.
Optimises for feasibility first, then time/cost/convenience.
"""

import json
import re
from src.utils.llm import call_agent
from src.utils.state import TripState, RouteOption, Leg, TripType

SYSTEM_PROMPT = """
You are the Route Planning Agent.

Your job is to decide whether the requested journey is:
1. direct_domestic — direct flight or train is available
2. direct_international — flight-based journey
3. indirect_multimodal — no direct option, requires transit hubs and last-mile transport

If direct travel is not feasible, identify the best reachable intermediate hubs.
Construct realistic end-to-end route candidates using flights, trains, and ground transport.

Rules:
- Always optimize for feasibility first, then time, cost, and convenience.
- Never recommend an itinerary with unrealistic transfer timing (minimum 90 min for flights, 30 min for trains).
- If destination is in a small town/district, check for nearest major hubs.
- Return structured route candidates ONLY as valid JSON.
- Mark field as "unknown" if data is unavailable — do NOT hallucinate.
"""


def run(state: TripState) -> TripState:
    state.log("route_agent", "running", f"Planning routes: {state.intent.origin} → {state.intent.destination}")

    messages = [
        {
            "role": "user",
            "content": f"""
Plan all realistic route options for this journey:

ORIGIN: {state.intent.origin}
DESTINATION: {state.intent.destination}
DATE: {state.intent.travel_date}
PASSENGERS: {state.intent.passenger_count}
PRIORITIES: {state.intent.priorities}
TRIP TYPE: {state.intent.trip_type.value}

Return valid JSON:
{{
  "route_type": "direct_domestic | direct_international | indirect_multimodal",
  "feasibility_summary": "1-2 sentence summary",
  "transit_hubs": ["hub1", "hub2"],
  "options": [
    {{
      "option_id": "option_1",
      "legs": [
        {{
          "mode": "flight | train | bus | taxi",
          "origin": "<city/station>",
          "destination": "<city/station>",
          "departure_time": "<HH:MM or 'varies'>",
          "arrival_time": "<HH:MM or 'varies'>",
          "duration_minutes": 90,
          "carrier": "<airline/train name or 'various'>",
          "fare_inr": 3500,
          "booking_class": "<economy/sleeper/etc or 'varies'>",
          "notes": ""
        }}
      ],
      "total_duration_minutes": 300,
      "total_fare_inr": 5000,
      "transfer_count": 1,
      "risk_notes": ["List any risks or reliability concerns"]
    }}
  ]
}}

Generate 2-3 realistic options. Use real Indian city names, realistic fares and durations.
""",
        }
    ]

    result = call_agent(SYSTEM_PROMPT, messages, use_thinking=True)

    text = result["text"]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())

            # Update trip type if route agent has a more specific classification
            route_type = data.get("route_type", "")
            if route_type and route_type in TripType._value2member_map_:
                state.intent.trip_type = TripType(route_type)

            options = []
            for i, opt_data in enumerate(data.get("options", [])):
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

                option = RouteOption(
                    option_id=opt_data.get("option_id", f"option_{i+1}"),
                    legs=legs,
                    total_duration_minutes=int(opt_data.get("total_duration_minutes", 0)),
                    total_fare_inr=float(opt_data.get("total_fare_inr", 0)),
                    transfer_count=int(opt_data.get("transfer_count", 0)),
                    risk_notes=opt_data.get("risk_notes", []),
                )
                options.append(option)

            state.route_options = options
            state.log(
                "route_agent",
                "done",
                f"{len(options)} route(s) found | Type: {state.intent.trip_type.value}",
            )
        except (json.JSONDecodeError, ValueError) as e:
            state.add_error(f"Route planning parse error: {e}")
    else:
        state.add_error("Route agent returned no parseable JSON")

    return state
