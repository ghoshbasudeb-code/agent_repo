# agent_runtime/graph.py
from typing import TypedDict, Annotated, List
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

# 1. Define Execution State Schema
class ConversationState(TypedDict):
    messages: Annotated[List[dict], add_messages]
    context: List[str]
    requires_approval: bool

# 2. Define Node Functions
def retrieve_node(state: ConversationState):
    # Simulate retrieving vector context
    query = state["messages"][-1]["content"]
    retrieved_docs = [f"Context doc related to: {query}"]
    return {"context": retrieved_docs}

def reasoning_node(state: ConversationState):
    # Determine if action requires HITL approval
    last_msg = state["messages"][-1]["content"]
    if "transfer money" in last_msg.lower():
        return {"requires_approval": True}
    return {"requires_approval": False}

def router_edge(state: ConversationState):
    if state["requires_approval"]:
        return "human_approval"
    return "generate_response"

# 3. Build Graph
builder = StateGraph(ConversationState)
builder.add_node("retrieve", retrieve_node)
builder.add_node("reason", reasoning_node)

builder.add_edge(START, "retrieve")
builder.add_edge("retrieve", "reason")
builder.add_conditional_edges("reason", router_edge, {
    "human_approval": END,
    "generate_response": END
})

# Compile with persistent memory checkpointer
checkpointer = MemorySaver()
app_graph = builder.compile(checkpointer=checkpointer)