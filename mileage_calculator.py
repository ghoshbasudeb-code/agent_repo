import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

# ==========================================
# 1. DATABASE SETUP FOR AUDIT & MEMORY
# ==========================================
DB_FILE = "airport_distance_logs.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS distance_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            origin_airport TEXT,
            destination_airport TEXT,
            distance_nmi REAL,
            distance_km REAL,
            critique TEXT,
            is_approved INTEGER,
            retry_count INTEGER
        )
    """)
    conn.commit()
    conn.close()


def save_log(state: dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO distance_logs 
        (timestamp, origin_airport, destination_airport, distance_nmi, distance_km, critique, is_approved, retry_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        #datetime.utcnow().isoformat(),
        datetime.now(timezone.utc).isoformat(),
        state.get("origin_code"),
        state.get("destination_code"),
        state.get("distance_nmi"),
        state.get("distance_km"),
        state.get("critique"),
        1 if state.get("is_approved") else 0,
        state.get("retry_count", 0)
    ))
    conn.commit()
    conn.close()


init_db()


# ==========================================
# 2. DEFINE AGENT STATE
# ==========================================
class DistanceState(TypedDict):
    origin_query: str
    destination_query: str
    origin_code: Optional[str]
    origin_coords: Optional[dict]  # {"lat": float, "lon": float}
    destination_code: Optional[str]
    destination_coords: Optional[dict]
    distance_nmi: Optional[float]
    distance_km: Optional[float]
    summary_report: Optional[str]
    critique: Optional[str]
    retry_count: int
    is_approved: bool


# ==========================================
# 3. HELPER MATH FUNCTION (HAVERSINE)
# ==========================================
def calculate_haversine(lat1: float, lon1: float, lat2: float, lon2: float):
    """Calculates Great Circle distance between two coordinates."""
    R_KM = 6371.0088
    R_NMI = 3440.065

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return round(c * R_NMI, 2), round(c * R_KM, 2)


# Initialize LLM
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)


# ==========================================
# 4. DEFINE LANGGRAPH NODES
# ==========================================
def airport_resolver_node(state: DistanceState) -> dict:
    """Uses LLM structured output to resolve query to IATA code & Coordinates."""
    system_prompt = (
        "You are an aviation geography database. Convert the requested airport/city query "
        "into strict JSON containing:\n"
        "1. IATA/ICAO code (e.g., 'DFW', 'LHR')\n"
        "2. Latitude (decimal degrees)\n"
        "3. Longitude (decimal degrees)\n\n"
        "Format output ONLY as JSON:\n"
        '{"origin": {"code": "...", "lat": 0.0, "lon": 0.0}, "destination": {"code": "...", "lat": 0.0, "lon": 0.0}}'
    )

    user_prompt = f"Origin: {state['origin_query']}\nDestination: {state['destination_query']}"
    if state.get("critique"):
        user_prompt += f"\n\nPrevious Issue to fix:\n{state['critique']}"

    res = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])

    try:
        data = json.loads(res.content.strip().replace("```json", "").replace("```", ""))
        return {
            "origin_code": data["origin"]["code"],
            "origin_coords": {"lat": data["origin"]["lat"], "lon": data["origin"]["lon"]},
            "destination_code": data["destination"]["code"],
            "destination_coords": {"lat": data["destination"]["lat"], "lon": data["destination"]["lon"]},
            "retry_count": state.get("retry_count", 0)
        }
    except Exception as e:
        return {"critique": f"Failed to parse airport data: {str(e)}"}

def distance_calculator_node(state: DistanceState) -> dict:
    orig = state.get("origin_coords")
    dest = state.get("destination_coords")

    if not orig or not dest:
        return {"critique": "Missing coordinates for distance calculation."}

    nmi, km = calculate_haversine(orig["lat"], orig["lon"], dest["lat"], dest["lon"])
    miles = round(nmi * 1.15078, 2)  # Convert Nautical Miles to Statute Miles

    report = (
        f"Flight Distance Calculation:\n"
        f"Route: {state['origin_code']} -> {state['destination_code']}\n"
        f"Origin Coordinates: ({orig['lat']}, {orig['lon']})\n"
        f"Destination Coordinates: ({dest['lat']}, {dest['lon']})\n"
        f"Great Circle Distance:\n"
        f"  - {miles:,} Statute Miles\n"
        f"  - {nmi:,} Nautical Miles\n"
        f"  - {km:,} Kilometers"
    )

    return {
        "distance_nmi": nmi,
        "distance_km": km,
        "summary_report": report
    }
"""
def distance_calculator_node(state: DistanceState) -> dict:
    Computes exact spatial distances between coordinates.
    orig = state.get("origin_coords")
    dest = state.get("destination_coords")

    if not orig or not dest:
        return {"critique": "Missing coordinates for distance calculation."}

    nmi, km = calculate_haversine(orig["lat"], orig["lon"], dest["lat"], dest["lon"])

    report = (
        f"Flight Distance Calculation:\n"
        f"Route: {state['origin_code']} -> {state['destination_code']}\n"
        f"Origin Coordinates: ({orig['lat']}, {orig['lon']})\n"
        f"Destination Coordinates: ({dest['lat']}, {dest['lon']})\n"
        f"Great Circle Distance: {nmi:,} Nautical Miles ({km:,} km)"
    )

    return {
        "distance_nmi": nmi,
        "distance_km": km,
        "summary_report": report
    }

"""
def critic_node(state: DistanceState) -> dict:
    """Evaluates mathematical, logical, and geographical validity."""
    system_prompt = (
        "You are an Aviation Data Quality Control Manager.\n"
        "Inspect the route analysis for:\n"
        "1. Valid Coordinates: Latitude between -90 and 90, Longitude between -180 and 180.\n"
        "2. Non-zero Distance: Unless origin and destination are identical.\n"
        "3. Correct Code Resolution.\n\n"
        "If correct, start with 'APPROVED'.\n"
        "If flawed, start with 'NEEDS REVISION' and detail the error."
    )

    user_content = (
        f"Route: {state.get('origin_code')} to {state.get('destination_code')}\n"
        f"Report:\n{state.get('summary_report')}"
    )

    res = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_content)])
    text = res.content.strip()

    return {
        "critique": text,
        "is_approved": text.startswith("APPROVED"),
        "retry_count": state.get("retry_count", 0) + 1
    }


def persist_evaluation_node(state: DistanceState) -> dict:
    save_log(state)
    return {}


# ==========================================
# 5. WORKFLOW ROUTING
# ==========================================
def should_continue(state: DistanceState) -> str:
    if state.get("is_approved") or state.get("retry_count", 0) >= 3:
        return "persist"
    print(f"\n[Reflexion Loop Iteration {state['retry_count']}] Correcting resolution errors...")
    return "revise"


workflow = StateGraph(DistanceState)

workflow.add_node("resolve_airports", airport_resolver_node)
workflow.add_node("calculate_distance", distance_calculator_node)
workflow.add_node("critic", critic_node)
workflow.add_node("persist_evaluation", persist_evaluation_node)

workflow.set_entry_point("resolve_airports")
workflow.add_edge("resolve_airports", "calculate_distance")
workflow.add_edge("calculate_distance", "critic")

workflow.add_conditional_edges(
    "critic",
    should_continue,
    {
        "revise": "resolve_airports",
        "persist": "persist_evaluation"
    }
)

workflow.add_edge("persist_evaluation", END)
app = workflow.compile()


# ==========================================
# 6. INTERACTIVE EXECUTION LOOP
# ==========================================
def run_interactive_agent():
    print("==================================================")
    print(" Interactive Airport Distance Agent (LangGraph) ")
    print(" Type 'exit' or 'quit' anytime to stop.")
    print("==================================================\n")

    while True:
        try:
            origin_query = input("\nEnter Origin Airport or City: ").strip()
            if origin_query.lower() in ["exit", "quit"]:
                print("Exiting calculator. Goodbye!")
                break

            destination_query = input("Enter Destination Airport or City: ").strip()
            if destination_query.lower() in ["exit", "quit"]:
                print("Exiting calculator. Goodbye!")
                break

            if not origin_query or not destination_query:
                print("Both origin and destination are required. Please try again.")
                continue

            print("\nProcessing request through LangGraph pipeline...")
            initial_input = {
                "origin_query": origin_query,
                "destination_query": destination_query
            }

            result = app.invoke(initial_input)

            print("\n================ FINAL FLIGHT MILEAGE REPORT ================")
            print(result.get("summary_report", "No report generated."))
            print("=============================================================")

        except KeyboardInterrupt:
            print("\nProgram interrupted. Exiting.")
            break
        except Exception as e:
            print(f"\nAn error occurred: {str(e)}")


if __name__ == "__main__":
    run_interactive_agent()