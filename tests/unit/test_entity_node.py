import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.models.agent_state import AgentState


def _make_state(
    *,
    address: str | None = None,
    caller_name: str | None = None,
    message: str = "123 Main Street, Dubai",
) -> AgentState:
    return AgentState(
        call_sid="CA123",
        tenant_id="t_abc",
        caller_phone="+15551234567",
        address=address,
        caller_name=caller_name,
        conversation_history=[{"role": "user", "content": message}],
    )


@pytest.mark.asyncio
async def test_entity_node_all_present_returns_without_llm():
    state = _make_state(
        address="123 Main Street, Dubai",
        caller_name="Ahmed",
        message="that's correct",
    )

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock()

    with patch("nodes.entity_node.ChatOpenAI", return_value=mock_llm):
        from nodes.entity_node import entity_node

        result = await entity_node(state)

    mock_llm.ainvoke.assert_not_called()
    assert result.address == "123 Main Street, Dubai"
    assert result.caller_name == "Ahmed"
    assert result.agent_response is None


@pytest.mark.asyncio
async def test_entity_node_address_missing_sets_address_prompt():
    state = _make_state(message="my water heater is still leaking")

    mock_response = MagicMock()
    mock_response.content = json.dumps({})

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("nodes.entity_node.ChatOpenAI", return_value=mock_llm):
        from nodes.entity_node import entity_node

        result = await entity_node(state)

    mock_llm.ainvoke.assert_awaited_once()
    assert result.address is None
    assert result.caller_name is None
    assert result.agent_response == "What's the address for the service?"


@pytest.mark.asyncio
async def test_entity_node_caller_name_missing_sets_name_prompt():
    state = _make_state(
        address="123 Main Street, Dubai",
        message="123 Main Street, Dubai",
    )

    mock_response = MagicMock()
    mock_response.content = json.dumps({"address": "123 Main Street, Dubai"})

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("nodes.entity_node.ChatOpenAI", return_value=mock_llm):
        from nodes.entity_node import entity_node

        result = await entity_node(state)

    mock_llm.ainvoke.assert_awaited_once()
    assert result.address == "123 Main Street, Dubai"
    assert result.caller_name is None
    assert result.agent_response == "And what's your name?"
