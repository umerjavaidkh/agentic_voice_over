# services/agent-brain/nodes/qualifier_node.py

from shared.models.agent_state import AgentState

CONFIRM_WORDS = ["yes", "yeah", "sure", "go ahead", "book it", "ok", "confirm"]
DENY_WORDS = ["no", "cancel", "wait", "hold on", "not yet"]


async def qualifier_node(state: AgentState) -> AgentState:
    tech = state.assigned_technician

    if state.is_emergency:
        state.agent_response = (
            f"That sounds urgent. I can have {tech.name} at "
            f"{state.address} within {tech.eta_minutes} minutes. "
            f"The estimate is ${state.estimate_min:.0f}–${state.estimate_max:.0f}. "
            f"Shall I confirm that booking?"
        )
    else:
        state.agent_response = (
            f"I can schedule a technician to come out. "
            f"We have availability tomorrow between 9 AM and 12 PM. "
            f"The estimate is ${state.estimate_min:.0f}–${state.estimate_max:.0f}. "
            f"Does that work for you?"
        )

    return state


def should_dispatch(state: AgentState) -> str:
    """Conditional edge: did caller confirm?"""
    last = state.conversation_history[-1]["content"].lower()

    if any(word in last for word in CONFIRM_WORDS):
        return "dispatch"
    if any(word in last for word in DENY_WORDS):
        return "clarify"
    return "re_ask"
