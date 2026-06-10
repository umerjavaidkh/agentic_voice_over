# services/agent-brain/nodes/intent_node.py

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from prompts import get_response_prompt, get_system_prompt
from shared.models.agent_state import AgentState, ServiceCategory, UrgencyLevel


async def intent_node(
    state: AgentState,
    *,
    system_prompt: str | None = None,
    address_follow_up: str | None = None,
) -> AgentState:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    last_message = state.conversation_history[-1]["content"]

    response = await llm.ainvoke([
        SystemMessage(content=system_prompt or get_system_prompt("intent")),
        HumanMessage(content=last_message),
    ])

    data = json.loads(response.content)
    state.problem_description = data["problem_description"]
    state.service_category = ServiceCategory(data["service_category"])
    state.appliance_type = data.get("appliance_type")
    state.urgency_level = UrgencyLevel(data["urgency_signal"])
    state.is_emergency = state.urgency_level == UrgencyLevel.EMERGENCY

    state.agent_response = address_follow_up or get_response_prompt("intent")
    return state
