"""
Search Agent — Flight, Train, and Ground Transport
Three specialist searchers combined. Each enriches the state with realistic options.
In production these would call live APIs (Skyscanner, IRCTC, etc.).
"""

from src.utils.llm import call_agent
from src.utils.json_utils import extract_json
from src.utils.state import TripState

FLIGHT_SYSTEM = """
You are the Flight Search Agent.
Find realistic flight options for the requested leg.
Return ONLY valid JSON. Do not rank against trains or buses.
If no direct flight exists, explicitly state that.
Do NOT hallucinate flight numbers. Use realistic Indian airline options (IndiGo, Air India, SpiceJet, Vistara/Air India Express).
Mark any unavailable field as "unknown".
"""

TRAIN_SYSTEM = """
You are the Train Search Agent.
Find realistic train options for the requested rail leg.
Use real Indian Railways train names and numbers where known.
Return ONLY valid JSON.
Highlight station-level practicality for connecting itineraries.
Do NOT hallucinate train numbers. Mark unavailable fields as "unknown".
"""

GROUND_SYSTEM = """
You are the Ground Transport Agent.
Plan bus/taxi/auto-rickshaw/local transfer legs for last-mile connectivity.
Return ONLY valid JSON.
If a last-mile leg is uncertain, explicitly mark reliability as "uncertain".
Do NOT invent precise schedules when only estimates are available.
"""


def _search_flights(state: TripState) -> dict:
    """Search flights for each flight leg in route options."""
    flight_legs = []
    for opt in state.route_options:
        for leg in opt.legs:
            if leg.mode == "flight":
                flight_legs.append(f"{leg.origin} → {leg.destination}")

    if not flight_legs:
        return {}

    messages = [
        {
            "role": "user",
            "content": f"""
Find realistic flight options for these legs:
{chr(10).join(set(flight_legs))}

DATE: {state.intent.travel_date}
PASSENGERS: {state.intent.passenger_count}

Return JSON:
{{
  "flights": [
    {{
      "origin": "<city>",
      "destination": "<city>",
      "airline": "<name>",
      "flight_number": "<code or 'varies'>",
      "departure_time": "<HH:MM>",
      "arrival_time": "<HH:MM>",
      "duration_minutes": 90,
      "fare_inr": 4500,
      "baggage": "15kg included",
      "booking_status": "available | limited | unknown"
    }}
  ]
}}
""",
        }
    ]
    result = call_agent(FLIGHT_SYSTEM, messages)
    text = result["text"]
    return extract_json(text) or {}


def _search_trains(state: TripState) -> dict:
    """Search trains for each rail leg in route options."""
    train_legs = []
    for opt in state.route_options:
        for leg in opt.legs:
            if leg.mode == "train":
                train_legs.append(f"{leg.origin} → {leg.destination}")

    if not train_legs:
        return {}

    messages = [
        {
            "role": "user",
            "content": f"""
Find realistic train options for these legs:
{chr(10).join(set(train_legs))}

DATE: {state.intent.travel_date}
PASSENGERS: {state.intent.passenger_count}

Return JSON:
{{
  "trains": [
    {{
      "origin_station": "<station name>",
      "destination_station": "<station name>",
      "train_name": "<name>",
      "train_number": "<number or 'varies'>",
      "departure_time": "<HH:MM>",
      "arrival_time": "<HH:MM>",
      "duration_minutes": 480,
      "classes_available": ["SL", "3A", "2A"],
      "fare_inr": {{
        "SL": 350,
        "3A": 950,
        "2A": 1400
      }},
      "booking_status": "available | waitlisted | unknown"
    }}
  ]
}}
""",
        }
    ]
    result = call_agent(TRAIN_SYSTEM, messages)
    text = result["text"]
    return extract_json(text) or {}


def _search_ground(state: TripState) -> dict:
    """Search ground transport for taxi/bus legs."""
    ground_legs = []
    for opt in state.route_options:
        for leg in opt.legs:
            if leg.mode in ("bus", "taxi", "auto"):
                ground_legs.append(f"{leg.origin} → {leg.destination}")

    if not ground_legs:
        return {}

    messages = [
        {
            "role": "user",
            "content": f"""
Plan ground transport for these legs:
{chr(10).join(set(ground_legs))}

Return JSON:
{{
  "ground_transport": [
    {{
      "origin": "<location>",
      "destination": "<location>",
      "mode": "bus | taxi | shared_taxi | auto",
      "duration_minutes": 120,
      "fare_inr": 800,
      "reliability": "high | medium | uncertain",
      "schedule": "fixed | flexible",
      "notes": ""
    }}
  ]
}}
""",
        }
    ]
    result = call_agent(GROUND_SYSTEM, messages)
    text = result["text"]
    return extract_json(text) or {}


def run(state: TripState) -> TripState:
    state.log("search_agent", "running", "Searching flights, trains, and ground transport in parallel")

    # These run sequentially here; in production use asyncio.gather for true parallelism
    flight_data = _search_flights(state)
    train_data = _search_trains(state)
    ground_data = _search_ground(state)

    state.flight_results = flight_data.get("flights", [])
    state.train_results = train_data.get("trains", [])
    state.ground_transport_results = ground_data.get("ground_transport", [])

    total = len(state.flight_results) + len(state.train_results) + len(state.ground_transport_results)
    state.log(
        "search_agent",
        "done",
        f"Found: {len(state.flight_results)} flights | {len(state.train_results)} trains | {len(state.ground_transport_results)} ground options",
    )
    return state
