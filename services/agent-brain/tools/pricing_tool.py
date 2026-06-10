# services/agent-brain/tools/pricing_tool.py

from shared.models.agent_state import AgentState


async def run_pricing_tool(state: AgentState) -> AgentState:
    from pricing_service.client import PricingClient

    if not state.problem_description:
        return state

    result = await PricingClient().lookup(
        description=state.problem_description,
        category=state.service_category,
        tenant_id=state.tenant_id,
    )

    state.estimate_min = result.min_price
    state.estimate_max = result.max_price
    state.pricing_confidence = result.confidence
    return state
