# services/agent-brain/tools/geo_tool.py

from shared.models.agent_state import AgentState
from shared.utils.geo import find_nearest_technician


async def run_geo_tool(state: AgentState) -> AgentState:
    if not state.address:
        return state

    tech = await find_nearest_technician(
        address=state.address,
        category=state.service_category,
        tenant_id=state.tenant_id,
        is_emergency=state.is_emergency,
    )

    state.assigned_technician = tech
    state.dispatch_eta = (
        f"within {tech.eta_minutes} minutes"
        if state.is_emergency
        else "during your scheduled window"
    )
    return state
