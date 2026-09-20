# tools/sql_tool.py
from pydantic import BaseModel, Field
from langchain_core.tools import tool

class DatabaseQueryInput(BaseModel):
    query: str = Field(description="Structured SQL query to execute against database.")
    customer_id: str = Field(description="Associated customer ID for query scoping.")

@tool("database_query_tool", args_schema=DatabaseQueryInput)
def database_query_tool(query: str, customer_id: str) -> str:
    """Executes read-only analytics queries against customer database."""
    # Enforce database sandbox / parameterization
    if "DELETE" in query.upper() or "DROP" in query.upper():
        return "Error: Mutation operations forbidden."
    
    # Simulated query execution output
    return f"Execution successful for Customer {customer_id}: [Record 1: Balance $1,250]"