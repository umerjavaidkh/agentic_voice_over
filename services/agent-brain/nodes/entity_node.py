# services/agent-brain/nodes/entity_node.py

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from prompts import get_response_prompt, get_system_prompt
from shared.models.agent_state import AgentState

REQUIRED_ENTITIES = ["address", "caller_name"]
OPTIONAL_ENTITIES = ["appliance_age_years"]


async def entity_node(
    state: AgentState,
    *,
    system_prompt: str | None = None,
) -> AgentState:
    collected = {}
    if state.address:
        collected["address"] = state.address
    if state.caller_name:
        collected["caller_name"] = state.caller_name

    missing = [entity for entity in REQUIRED_ENTITIES if entity not in collected]

    if not missing:
        return state

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    last_message = state.conversation_history[-1]["content"]

    prompt_template = system_prompt or get_system_prompt("entity")
    response = await llm.ainvoke([
        SystemMessage(content=prompt_template.format(
            collected=collected,
            missing=missing,
            message=last_message,
        )),
    ])

    data = json.loads(response.content)
    if "address" in data:
        state.address = data["address"]
    if "caller_name" in data:
        state.caller_name = data["caller_name"]
    if "appliance_age_years" in data:
        state.appliance_age_years = data["appliance_age_years"]

    still_missing = [entity for entity in REQUIRED_ENTITIES if not getattr(state, entity)]
    if still_missing:
        state.agent_response = get_response_prompt("entity", field=still_missing[0])

    return state
