# services/agent-brain/tools/pricing_tool.py

from shared.models.agent_state import AgentState


async def run_pricing_tool(state: AgentState) -> dict:
    from pricing_service.client import PricingClient

    if not state.problem_description:
        return {}

    result = await PricingClient().lookup(
        description=state.problem_description,
        category=state.service_category,
        tenant_id=state.tenant_id,
        is_emergency=state.is_emergency,
    )

    return {
        "estimate_min": result.min_price,
        "estimate_max": result.max_price,
        "pricing_confidence": result.confidence,
    }
