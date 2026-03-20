"""
Orchestrator Agent
Classifies intent, routes to specialist agents, and drives the overall flow.
"""

from src.utils.llm import call_agent
from src.utils.json_utils import extract_json
from src.utils.state import TripState, TripType

SYSTEM_PROMPT = """
You are the Supervisor Agent of a production-grade multi-agent travel planning and booking system.
Your job is to understand user travel intent, coordinate specialist agents, validate route feasibility,
compare travel options, and only initiate booking operations after explicit user confirmation.

Given a user journey request originating from Delhi, you must:
1. Understand the destination and classify the trip type
2. Identify what specialist agents are needed
3. Generate a structured plan
4. Maintain robustness, traceability, and fallback handling at every step

SUPPORTED SCENARIO TYPES:
A. DIRECT DOMESTIC ROUTE - Example: Delhi → Patna (direct flight or train available)
B. DIRECT INTERNATIONAL ROUTE - Example: Delhi → Dubai (flight-based)
C. INDIRECT OR MULTI-MODAL ROUTE - Example: Delhi → Banka, Bihar (no direct option, needs hubs)

You must classify the route type and identify the correct agents to invoke.
Respond with a structured JSON plan.
"""


def run(state: TripState) -> TripState:
    state.log("orchestrator", "running", "Classifying intent and building execution plan")

    messages = [
        {
            "role": "user",
            "content": f"""
Analyse this travel request and return a structured JSON response:

REQUEST: {state.user_request}

Return JSON with these fields:
{{
  "trip_type": "direct_domestic" | "direct_international" | "indirect_multimodal",
  "agents_needed": ["intent_extraction", "route_planning", "flight_search", "train_search", "ground_transport"],
  "reasoning": "brief explanation of classification",
  "missing_critical_info": ["travel_date", "passenger_count"] // list only truly missing critical fields
}}
""",
        }
    ]

    result = call_agent(SYSTEM_PROMPT, messages, use_thinking=True)

    data = extract_json(result["text"])
    if data:
        trip_type_str = data.get("trip_type", "unknown")
        try:
            state.intent.trip_type = TripType(trip_type_str)
        except ValueError:
            state.intent.trip_type = TripType.UNKNOWN
        state.log("orchestrator", "done", f"Trip type: {state.intent.trip_type.value} | Agents: {data.get('agents_needed', [])}")
    else:
        state.intent.trip_type = TripType.UNKNOWN
        state.log("orchestrator", "done", "Classification complete (fallback)")

    return state
