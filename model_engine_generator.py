# model_engine/generator.py
import os
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

def generate_grounded_response(user_query: str, retrieved_context: list[str]) -> str:
    # 1. Assemble System Context Prompt
    formatted_context = "\n---\n".join(retrieved_context)
    system_instruction = (
        "You are an Enterprise Conversational AI Assistant. "
        "Answer the user's query STRICTLY based on the provided Context below. "
        "If the information is not contained in the Context, state 'I cannot find relevant records.'\n\n"
        f"CONTEXT:\n{formatted_context}"
    )

    # 2. Set Generation Config (Temperature, Top-P)
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.2, # Low temperature for factual grounding
        top_p=0.95,
        max_output_tokens=1024
    )

    # 3. Call Foundation Model (Decoder-Only Architecture)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_query,
        config=config
    )
    
    return response.text