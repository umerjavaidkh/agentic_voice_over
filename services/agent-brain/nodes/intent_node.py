# services/agent-brain/nodes/intent_node.py

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from shared.models.agent_state import AgentState, ServiceCategory, UrgencyLevel

INTENT_SYSTEM_PROMPT = """
You are an expert at understanding home service problems from brief phone descriptions.

Extract from the caller's message:
1. problem_description: one clear sentence describing the issue
2. service_category: one of [plumbing, hvac, roofing, electrical, general]
3. appliance_type: specific appliance if mentioned (e.g. "water heater", "AC unit", "furnace")
4. urgency_signal: one of [emergency, urgent, normal]
   - emergency: active leak, no heat in winter, safety risk, "right now", "badly", "flooding"
   - urgent: not working, broken, "as soon as possible"
   - normal: maintenance, intermittent issue, "when you have time"

Return ONLY valid JSON. No explanation.
"""


async def intent_node(state: AgentState) -> AgentState:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    last_message = state.conversation_history[-1]["content"]

    response = await llm.ainvoke([
        SystemMessage(content=INTENT_SYSTEM_PROMPT),
        HumanMessage(content=last_message),
    ])

    data = json.loads(response.content)
    state.problem_description = data["problem_description"]
    state.service_category = ServiceCategory(data["service_category"])
    state.appliance_type = data.get("appliance_type")
    state.urgency_level = UrgencyLevel(data["urgency_signal"])
    state.is_emergency = state.urgency_level == UrgencyLevel.EMERGENCY

    # Ask for address next
    state.agent_response = "Got it. What's the address where you need the service?"
    return state
