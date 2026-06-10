import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.models.agent_state import AgentState, ServiceCategory, Technician, UrgencyLevel


def _intent_llm_response():
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "problem_description": "Water heater leaking badly",
        "service_category": "plumbing",
        "appliance_type": "water heater",
        "urgency_signal": "emergency",
    })
    return mock_response


def _make_initial_state(*, last_message: str = "yes book it") -> AgentState:
    return AgentState(
        call_sid="CA123",
        tenant_id="t_abc",
        caller_phone="+15551234567",
        caller_name="Ahmed",
        address="123 Main Street, Dubai",
        conversation_history=[{"role": "user", "content": last_message}],
    )


@pytest.fixture
def graph_mocks():
    mock_pricing_result = MagicMock()
    mock_pricing_result.min_price = 200.0
    mock_pricing_result.max_price = 450.0
    mock_pricing_result.confidence = 0.91

    mock_pricing_client = MagicMock()
    mock_pricing_client.lookup = AsyncMock(return_value=mock_pricing_result)

    tech = Technician(
        tech_id="tech_1",
        name="Mike",
        phone="+15559876543",
        distance_km=4.2,
        eta_minutes=45,
        specialty=ServiceCategory.PLUMBING,
    )

    mock_dispatch_client = MagicMock()
    mock_dispatch_client.create_job = AsyncMock(
        return_value={
            "job_id": "JOB-12345",
            "booking_confirmed": True,
            "confirmation_number": "JOB-12345",
            "business_name": "Dallas Plumbing Co.",
        }
    )

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=_intent_llm_response())

    mock_twilio_client = MagicMock()

    with (
        patch("nodes.intent_node.ChatOpenAI", return_value=mock_llm),
        patch("nodes.entity_node.ChatOpenAI", return_value=mock_llm),
        patch("pricing_service.client.PricingClient", return_value=mock_pricing_client),
        patch("tools.geo_tool.find_nearest_technician", new_callable=AsyncMock, return_value=tech),
        patch("nodes.dispatcher_node.DispatchClient", return_value=mock_dispatch_client),
        patch("sms.Client", return_value=mock_twilio_client),
        patch("sms.TWILIO_SID", "AC-test-sid"),
        patch("sms.TWILIO_TOKEN", "test-token"),
        patch("sms.TWILIO_FROM_NUMBER", "+12145550001"),
    ):
        yield {
            "dispatch_client": mock_dispatch_client,
            "pricing_client": mock_pricing_client,
        }


def test_build_graph_has_expected_nodes():
    from graph import build_graph

    graph = build_graph()
    node_names = set(graph.get_graph().nodes.keys())

    assert {
        "intent",
        "entity",
        "pricing",
        "geo_routing",
        "qualifier",
        "dispatcher",
        "__start__",
        "__end__",
    }.issubset(node_names)


@pytest.mark.asyncio
async def test_graph_happy_path_dispatches_and_books(graph_mocks):
    from graph import build_graph

    graph = build_graph()
    raw_result = await graph.ainvoke(_make_initial_state())
    result = AgentState(**raw_result) if isinstance(raw_result, dict) else raw_result

    assert result.problem_description == "Water heater leaking badly"
    assert result.service_category == ServiceCategory.PLUMBING
    assert result.urgency_level == UrgencyLevel.EMERGENCY
    assert result.is_emergency is True
    assert result.estimate_min == 200.0
    assert result.estimate_max == 450.0
    assert result.assigned_technician is not None
    assert result.assigned_technician.name == "Mike"
    assert result.job_id == "JOB-12345"
    assert result.booking_confirmed is True
    assert result.fallback_triggered is False
    graph_mocks["dispatch_client"].create_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_graph_dispatch_failure_triggers_fallback(graph_mocks):
    from graph import build_graph

    graph_mocks["dispatch_client"].create_job = AsyncMock(
        side_effect=RuntimeError("FSM API unavailable")
    )

    graph = build_graph()
    raw_result = await graph.ainvoke(_make_initial_state())
    result = AgentState(**raw_result) if isinstance(raw_result, dict) else raw_result

    assert result.booking_confirmed is False
    assert result.job_id is None
    assert result.fallback_triggered is True
    assert result.error_message == "FSM API unavailable"
    assert "having trouble completing the booking" in result.agent_response
