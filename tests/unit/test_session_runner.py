from unittest.mock import AsyncMock, MagicMock

import pytest

from session_runner import SessionRunner
from shared.models.agent_state import AgentState

TENANT_ID = "t_abc"


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.get_call_state = AsyncMock(return_value=None)
    redis.set_call_state = AsyncMock()
    return redis


@pytest.fixture
def mock_graph():
    graph = MagicMock()
    graph.ainvoke = AsyncMock()
    return graph


@pytest.fixture
def runner(mock_redis, mock_graph):
    return SessionRunner(mock_redis, mock_graph)


@pytest.mark.asyncio
async def test_process_turn_creates_new_agent_state_when_no_redis_key(runner, mock_redis, mock_graph):
    mock_redis.get_call_state.return_value = None
    result_state = AgentState(
        call_sid="CA123",
        tenant_id=TENANT_ID,
        turn_count=1,
        conversation_history=[{"role": "user", "content": "water heater leaking"}],
        agent_response="What is your address?",
    )
    mock_graph.ainvoke.return_value = result_state

    response = await runner.process_turn(TENANT_ID, "CA123", "water heater leaking")

    mock_redis.get_call_state.assert_awaited_once_with(TENANT_ID, "CA123")
    mock_graph.ainvoke.assert_awaited_once()
    invoked_state = mock_graph.ainvoke.await_args.args[0]
    assert invoked_state.call_sid == "CA123"
    assert invoked_state.tenant_id == TENANT_ID
    assert invoked_state.turn_count == 1
    assert invoked_state.conversation_history == [
        {"role": "user", "content": "water heater leaking"}
    ]
    assert response == "What is your address?"


@pytest.mark.asyncio
async def test_process_turn_loads_existing_state_and_increments_turn_count(runner, mock_redis, mock_graph):
    existing = AgentState(
        call_sid="CA123",
        tenant_id=TENANT_ID,
        caller_phone="+15551234567",
        turn_count=2,
        conversation_history=[{"role": "user", "content": "earlier turn"}],
    )
    mock_redis.get_call_state.return_value = existing.model_dump()

    result_state = AgentState(
        call_sid="CA123",
        tenant_id=TENANT_ID,
        caller_phone="+15551234567",
        turn_count=3,
        conversation_history=[
            {"role": "user", "content": "earlier turn"},
            {"role": "user", "content": "123 Main St"},
        ],
        agent_response="Got it.",
    )
    mock_graph.ainvoke.return_value = result_state

    await runner.process_turn(TENANT_ID, "CA123", "123 Main St")

    invoked_state = mock_graph.ainvoke.await_args.args[0]
    assert invoked_state.turn_count == 3
    assert invoked_state.conversation_history[-1] == {
        "role": "user",
        "content": "123 Main St",
    }


@pytest.mark.asyncio
async def test_process_turn_persists_state_to_redis_with_ttl_1800(runner, mock_redis, mock_graph):
    result_state = AgentState(
        call_sid="CA123",
        tenant_id=TENANT_ID,
        turn_count=1,
        conversation_history=[{"role": "user", "content": "hello"}],
        agent_response="Hi there.",
    )
    mock_graph.ainvoke.return_value = result_state

    await runner.process_turn(TENANT_ID, "CA123", "hello")

    mock_redis.set_call_state.assert_awaited_once_with(
        TENANT_ID,
        "CA123",
        result_state.model_dump(),
        ttl=1800,
    )


@pytest.mark.asyncio
async def test_process_turn_returns_agent_response_string(runner, mock_redis, mock_graph):
    mock_graph.ainvoke.return_value = AgentState(
        call_sid="CA123",
        tenant_id=TENANT_ID,
        agent_response="I can help with that leak.",
    )

    response = await runner.process_turn(TENANT_ID, "CA123", "my pipe burst")

    assert response == "I can help with that leak."
    assert isinstance(response, str)
