"""LangGraph multi-agent StateGraph.

Topology:
    START → router → [training | rehab | nutrition] → END

The Router Agent classifies user intent and refines the query.
One of the three Specialist Agents then retrieves relevant chunks,
builds a grounded prompt, and generates the final response.
"""
from langgraph.graph import END, START, StateGraph

from app.agents.router import route_by_agent, router_node
from app.agents.specialist import nutrition_node, rehab_node, training_node
from app.agents.state import AgentState

# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

_builder = StateGraph(AgentState)

_builder.add_node("router", router_node)
_builder.add_node("training", training_node)
_builder.add_node("rehab", rehab_node)
_builder.add_node("nutrition", nutrition_node)

_builder.add_edge(START, "router")
_builder.add_conditional_edges(
    "router",
    route_by_agent,
    {
        "training": "training",
        "rehab": "rehab",
        "nutrition": "nutrition",
    },
)
_builder.add_edge("training", END)
_builder.add_edge("rehab", END)
_builder.add_edge("nutrition", END)

# ---------------------------------------------------------------------------
# Compiled graph — import this in the chat API
# ---------------------------------------------------------------------------

agent_graph = _builder.compile()
