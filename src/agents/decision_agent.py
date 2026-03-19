"""
Decision + Ranking Agent
Ranks all route candidates by time, cost, convenience, and reliability.
Flags conflicts, fragile connections, and trade-offs.
Does not search for routes or execute bookings.
"""

from src.utils.llm import call_agent
from src.utils.json_utils import extract_json
from src.utils.state import TripState

SYSTEM_PROMPT = """
You are the Pricing & Ranking Agent combined with the Decision and Conflict Resolver Agent.

Compare all candidate itineraries across:
- total travel time
- estimated total cost
- number of transfers
- convenience (ease of travel, airport vs station, etc.)
- connection reliability (buffer time between legs)
- operational risk (cancellation risk, last-mile uncertainty)

Rank the options 1 = best.
Identify the single recommended option.
Explain trade-offs briefly and clearly.
Reject fragile itineraries with unrealistic connection times (<90 min for flights, <30 min for trains).
Return ONLY valid JSON.
"""


def _summarise_options(state: TripState) -> str:
    """Serialise route options into a compact string for the prompt."""
    lines = []
    for opt in state.route_options:
        lines.append(f"\nOption {opt.option_id}:")
        for leg in opt.legs:
            lines.append(
                f"  [{leg.mode.upper()}] {leg.origin} → {leg.destination} "
                f"| {leg.departure_time}-{leg.arrival_time} "
                f"| {leg.duration_minutes}min | ₹{leg.fare_inr} | {leg.carrier}"
            )
        lines.append(
            f"  Total: {opt.total_duration_minutes}min | ₹{opt.total_fare_inr} | {opt.transfer_count} transfer(s)"
        )
        if opt.risk_notes:
            lines.append(f"  Risks: {'; '.join(opt.risk_notes)}")
    return "\n".join(lines) if lines else "No options available"


def run(state: TripState) -> TripState:
    state.log("decision_agent", "running", "Ranking options and resolving conflicts")

    if not state.route_options:
        state.add_error("No route options to rank — decision agent cannot proceed")
        return state

    options_text = _summarise_options(state)

    messages = [
        {
            "role": "user",
            "content": f"""
Rank and evaluate these travel options:

JOURNEY: {state.intent.origin} → {state.intent.destination}
DATE: {state.intent.travel_date}
PASSENGERS: {state.intent.passenger_count}
PRIORITIES: {state.intent.priorities}

OPTIONS:
{options_text}

ADDITIONAL SEARCH DATA:
Flights found: {len(state.flight_results)}
Trains found: {len(state.train_results)}
Ground options: {len(state.ground_transport_results)}

Return JSON:
{{
  "ranked_options": [
    {{
      "option_id": "<id>",
      "rank": 1,
      "convenience_score": 8.5,
      "recommended": true,
      "trade_off_summary": "fastest but most expensive",
      "reject": false,
      "reject_reason": ""
    }}
  ],
  "recommended_option_id": "<id>",
  "comparison_summary": "2-3 sentence comparison of all options",
  "risks_and_constraints": ["list of key risks"]
}}
""",
        }
    ]

    result = call_agent(SYSTEM_PROMPT, messages, use_thinking=True)

    data = extract_json(result["text"])
    if data:
        ranked_map = {r["option_id"]: r for r in data.get("ranked_options", [])}

        ranked_options = []
        for opt in state.route_options:
            ranking = ranked_map.get(opt.option_id, {})
            if ranking.get("reject"):
                continue  # Drop fragile itineraries
            opt.rank = ranking.get("rank", 99)
            opt.convenience_score = float(ranking.get("convenience_score", 0.0))
            opt.recommended = bool(ranking.get("recommended", False))
            ranked_options.append(opt)

        ranked_options.sort(key=lambda o: o.rank)
        state.ranked_options = ranked_options
        state.recommended_option_id = data.get("recommended_option_id", "")
        state.summary = data.get("comparison_summary", "")

        state.log(
            "decision_agent",
            "done",
            f"{len(ranked_options)} option(s) ranked | Recommended: {state.recommended_option_id}",
        )
    else:
        state.add_error("Decision agent returned no parseable JSON")

    return state
