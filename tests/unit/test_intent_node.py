import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.models.agent_state import AgentState, ServiceCategory, UrgencyLevel


def _make_state(phrase: str) -> AgentState:
    return AgentState(
        call_sid="CA123",
        tenant_id="t_abc",
        caller_phone="+15551234567",
        conversation_history=[{"role": "user", "content": phrase}],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase,llm_payload,expected_urgency,expected_category",
    [
        (
            "My pipe burst and water is flooding the basement right now",
            {
                "problem_description": "Burst pipe flooding the basement",
                "service_category": "plumbing",
                "appliance_type": None,
                "urgency_signal": "emergency",
            },
            UrgencyLevel.EMERGENCY,
            ServiceCategory.PLUMBING,
        ),
        (
            "We have no heat at all and it's freezing, someone needs to come immediately",
            {
                "problem_description": "No heat in the home during freezing weather",
                "service_category": "hvac",
                "appliance_type": "furnace",
                "urgency_signal": "emergency",
            },
            UrgencyLevel.EMERGENCY,
            ServiceCategory.HVAC,
        ),
        (
            "My AC stopped working and it's 95 degrees, I need someone ASAP",
            {
                "problem_description": "AC unit not cooling during hot weather",
                "service_category": "hvac",
                "appliance_type": "AC unit",
                "urgency_signal": "urgent",
            },
            UrgencyLevel.URGENT,
            ServiceCategory.HVAC,
        ),
        (
            "Our water heater is broken, need a repair as soon as possible",
            {
                "problem_description": "Water heater is not working",
                "service_category": "plumbing",
                "appliance_type": "water heater",
                "urgency_signal": "urgent",
            },
            UrgencyLevel.URGENT,
            ServiceCategory.PLUMBING,
        ),
        (
            "I'd like to schedule annual HVAC maintenance when you have time",
            {
                "problem_description": "Request for routine HVAC maintenance",
                "service_category": "hvac",
                "appliance_type": "AC unit",
                "urgency_signal": "normal",
            },
            UrgencyLevel.NORMAL,
            ServiceCategory.HVAC,
        ),
    ],
)
async def test_intent_node_classifies_urgency(
    phrase,
    llm_payload,
    expected_urgency,
    expected_category,
):
    state = _make_state(phrase)

    mock_response = MagicMock()
    mock_response.content = json.dumps(llm_payload)

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("nodes.intent_node.ChatOpenAI", return_value=mock_llm):
        from nodes.intent_node import intent_node

        result = await intent_node(state)

    mock_llm.ainvoke.assert_awaited_once()
    assert result.urgency_level == expected_urgency
    assert result.is_emergency == (expected_urgency == UrgencyLevel.EMERGENCY)
    assert result.service_category == expected_category
    assert result.problem_description == llm_payload["problem_description"]
    assert result.appliance_type == llm_payload.get("appliance_type")
    assert result.agent_response == "Got it. What's the address where you need the service?"
