[200~import json
  from typing import List, TypedDict
  import requests

  from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
  from langchain_openai import ChatOpenAI
  from langgraph.graph import END, StateGraph


  # ==========================================
  # 1. DEFINE STATE SCHEMA
  # ==========================================
  class AgentState(TypedDict):
      latitude: float
      longitude: float
      weather_data: str
      forecast: str
      critique: str
      retry_count: int
      is_approved: bool


  # ==========================================
  # 2. HELPER TOOL: FETCH REAL WEATHER DATA
  # ==========================================
  def fetch_weather_api(lat: float, lon: float) -> str:
      """Fetches real-time weather data using Open-Meteo API (Free, no API key needed)."""
      url = (
                  f"https://api.open-meteo.com/v1/forecast?"
                          f"latitude={lat}&longitude={lon}&current_weather=true&"
                                  f"hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation_probability"
                                      )
      try:
          response = requests.get(url, timeout=10)
          response.raise_for_status()
          return json.dumps(response.json(), indent=2)
      except Exception as e:
          return f"Error fetching weather data: {str(e)}"


  # ==========================================
  # 3. LLM INITIALIZATION
  # ==========================================
  # Make sure OPENAI_API_KEY is set in your environment
  llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)


  # ==========================================
  # 4. DEFINE GRAPH NODES
  # ==========================================
  def fetch_weather_node(state: AgentState) -> dict:
        """Node to fetch raw data for the given coordinates."""
            raw_data = fetch_weather_api(state["latitude"], state["longitude"])
                return {"weather_data": raw_data, "retry_count": 0, "is_approved": False}


            def forecaster_node(state: AgentState) -> dict:
                    """Generator Node: Generates or revises the forecast based on feedback."""
                        system_prompt = (
                                        "You are an expert meteorological forecaster. Analyze the raw weather API data "
                                                "and draft a clear, professional weather forecast including current conditions, "
                                                        "temperature trend, wind speed, and precipitation chance. Give the temperature in"
                                                                "Fahrenheit and time in Central time zone. "
                                                                    )

                            user_content = f"Coordinates: ({state['latitude']}, {state['longitude']})\nRaw Data:\n{state['weather_data']}"

                                # If a prior critique exists, force the model to address it (self-improvement)
                                    if state.get("critique"):
                                                user_content += f"\n\n--- PREVIOUS CRITIQUE / CORRECTIONS NEEDED ---\n{state['critique']}\n\nPlease revise your forecast to address the critique above."

                                                    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
                                                        response = llm.invoke(messages)

                                                            return {"forecast": response.content}


                                                        def critic_node(state: AgentState) -> dict:
                                                                """Evaluator Node: Critiques the draft forecast for accuracy and completeness."""
                                                                    system_prompt = (
                                                                                    "You are a strict Quality Control Manager for weather reporting.\n"
                                                                                            "Evaluate the draft forecast against the raw API data based on:\n"
                                                                                                    "1. Accuracy: Do numbers (temperature, wind speed, precipitation) match the raw data?\n"
                                                                                                            "2. Completeness: Does it specify units (°C/°F, km/h or mph) and give actionable insights?\n"
                                                                                                                    "3. Clarity: Is it structured logically?\n\n"
                                                                                                                            "If satisfactory, start your response with 'APPROVED'.\n"
                                                                                                                                    "If flaws or omissions exist, start with 'NEEDS REVISION' and list specific corrections."
                                                                                                                                        )

                                                                        user_content = (
                                                                                        f"Raw API Data:\n{state['weather_data']}\n\n"
                                                                                                f"Draft Forecast:\n{state['forecast']}"
                                                                                                    )

                                                                            messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
                                                                                response = llm.invoke(messages)
                                                                                    critique_text = response.content.strip()

                                                                                        is_approved = critique_text.startswith("APPROVED")
                                                                                            current_retries = state.get("retry_count", 0) + 1

                                                                                                return {
                                                                                                                "critique": critique_text,
                                                                                                                        "is_approved": is_approved,
                                                                                                                                "retry_count": current_retries
                                                                                                                                    }


                                                                                                # ==========================================
                                                                                                # 5. CONDITIONAL ROUTING EDGE
                                                                                                # ==========================================
                                                                                                def should_continue(state: AgentState) -> str:
                                                                                                        """Routes back to generator if critique failed, up to max retries."""
                                                                                                            MAX_RETRIES = 3
                                                                                                                if state["is_approved"] or state["retry_count"] >= MAX_RETRIES:
                                                                                                                            return "end"
                                                                                                                            print(f"\n[Reflexion Loop triggered - Iteration {state['retry_count']}] Correcting forecast errors...")
                                                                                                                                return "revise"


                                                                                                                            # ==========================================
                                                                                                                            # 6. BUILD THE LANGGRAPH
                                                                                                                            # ==========================================
                                                                                                                            workflow = StateGraph(AgentState)

                                                                                                                            # Add nodes
                                                                                                                            workflow.add_node("fetch_weather", fetch_weather_node)
                                                                                                                            workflow.add_node("forecaster", forecaster_node)
                                                                                                                            workflow.add_node("critic", critic_node)

                                                                                                                            # Add edges
                                                                                                                            workflow.set_entry_point("fetch_weather")
                                                                                                                            workflow.add_edge("fetch_weather", "forecaster")
                                                                                                                            workflow.add_edge("forecaster", "critic")

                                                                                                                            # Conditional edge from Critic -> Forecaster or END
                                                                                                                            workflow.add_conditional_edges(
                                                                                                                                        "critic",
                                                                                                                                            should_continue,
                                                                                                                                                {
                                                                                                                                                            "revise": "forecaster",
                                                                                                                                                                    "end": END
                                                                                                                                                                        }
                                                                                                                                                )

                                                                                                                            # Compile application
                                                                                                                            app = workflow.compile()

                                                                                                                            # ==========================================
                                                                                                                            # 7. EXECUTION
                                                                                                                            # ==========================================
                                                                                                                            if __name__ == "__main__":
                                                                                                                                    # Example: Trophy Club, TX (Lat: 32.9982, Lon: -97.1884)
                                                                                                                                        initial_input = {
                                                                                                                                                        "latitude": 32.9982,
                                                                                                                                                                "longitude": -97.1884
                                                                                                                                                                    }

                                                                                                                                            result = app.invoke(initial_input)

                                                                                                                                                print("\n================ FINAL WEATHER FORECAST ================")
                                                                                                                                                    print(result["forecast"])
                                                                                                                                                        print("\n================ FINAL EVALUATION STATUS ================")
                                                                                                                                                            print(result["critique"])
