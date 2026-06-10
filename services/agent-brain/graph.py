# services/agent-brain/graph.py

from langgraph.graph import END, StateGraph

from nodes.dispatcher_node import dispatcher_node
from nodes.entity_node import entity_node
from nodes.intent_node import intent_node
from nodes.qualifier_node import qualifier_node, should_dispatch
from shared.models.agent_state import AgentState
from tools.geo_tool import run_geo_tool
from tools.pricing_tool import run_pricing_tool


def build_graph():
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("intent", intent_node)
    graph.add_node("entity", entity_node)
    graph.add_node("pricing", run_pricing_tool)
    graph.add_node("geo_routing", run_geo_tool)
    graph.add_node("qualifier", qualifier_node)
    graph.add_node("dispatcher", dispatcher_node)

    # Edges
    graph.set_entry_point("intent")
    graph.add_edge("intent", "entity")

    # After entity: run pricing + geo in parallel
    graph.add_edge("entity", "pricing")
    graph.add_edge("entity", "geo_routing")
    graph.add_edge("pricing", "qualifier")
    graph.add_edge("geo_routing", "qualifier")

    # Qualifier conditional
    graph.add_conditional_edges(
        "qualifier",
        should_dispatch,
        {
            "dispatch": "dispatcher",
            "clarify": "qualifier",  # loop back
            "re_ask": "qualifier",
        },
    )

    graph.add_edge("dispatcher", END)
    return graph.compile()
