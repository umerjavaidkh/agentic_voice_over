import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from base import JobResult
from shared.models.agent_state import AgentState, ServiceCategory, Technician, UrgencyLevel


def _intent_llm_response():
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "problem_description": "water heater leaking",
        "service_category": "plumbing",
        "appliance_type": "water heater",
        "urgency_signal": "emergency",
    })
    return mock_response


def _make_booking_state() -> AgentState:
    return AgentState(
        call_sid="CA-integration-test",
        tenant_id="t_test",
        caller_phone="+15551234567",
        caller_name="Ahmed Khan",
        address="742 Evergreen Terrace, Dallas, TX",
        conversation_history=[
            {"role": "user", "content": "water heater leaking"},
            {"role": "user", "content": "yes book it"},
        ],
    )


@pytest.fixture
def booking_flow_mocks():
    mock_pricing_result = MagicMock()
    mock_pricing_result.min_price = 800.0
    mock_pricing_result.max_price = 1800.0
    mock_pricing_result.confidence = 0.87

    mock_pricing_client = MagicMock()
    mock_pricing_client.lookup = AsyncMock(return_value=mock_pricing_result)

    technician = Technician(
        tech_id="tech-42",
        name="Mike Torres",
        phone="+15559876543",
        distance_km=5.1,
        eta_minutes=45,
        specialty=ServiceCategory.PLUMBING,
    )

    service_titan_job = JobResult(
        job_id="ST-9001",
        booking_confirmed=True,
        tech_name="Mike Torres",
        tech_phone="+15559876543",
        eta_window="within 45 minutes",
        confirmation_number="ST-9001",
    )

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=_intent_llm_response())

    mock_twilio_client = MagicMock()

    mock_service_titan_adapter = MagicMock()
    mock_service_titan_adapter.create_job = AsyncMock(return_value=service_titan_job)

    with (
        patch("nodes.intent_node.ChatOpenAI", return_value=mock_llm),
        patch("pricing_service.client.PricingClient", return_value=mock_pricing_client),
        patch("tools.geo_tool.find_nearest_technician", new_callable=AsyncMock, return_value=technician),
        patch("factory.get_adapter", AsyncMock(return_value=mock_service_titan_adapter)),
        patch("adapters.service_titan.ServiceTitanAdapter.create_job", AsyncMock(return_value=service_titan_job)),
        patch("sms.Client", return_value=mock_twilio_client),
        patch("sms.TWILIO_SID", "AC-test-sid"),
        patch("sms.TWILIO_TOKEN", "test-token"),
        patch("sms.TWILIO_FROM_NUMBER", "+12145550001"),
    ):
        yield {
            "service_titan_adapter": mock_service_titan_adapter,
            "twilio_client": mock_twilio_client,
        }


@pytest.mark.asyncio
async def test_complete_booking_flow_without_voice(booking_flow_mocks):
    from graph import build_graph

    graph = build_graph()
    raw_result = await graph.ainvoke(_make_booking_state())
    result = AgentState(**raw_result) if isinstance(raw_result, dict) else raw_result

    assert result.problem_description == "water heater leaking"
    assert result.service_category == ServiceCategory.PLUMBING
    assert result.urgency_level == UrgencyLevel.EMERGENCY
    assert result.address == "742 Evergreen Terrace, Dallas, TX"
    assert result.booking_confirmed is True
    assert result.job_id is not None
    assert result.job_id == "ST-9001"
    assert result.estimate_min is not None
    assert result.estimate_min > 0
    assert result.assigned_technician is not None
    assert result.assigned_technician.name == "Mike Torres"

    booking_flow_mocks["service_titan_adapter"].create_job.assert_awaited_once()

    mock_twilio = booking_flow_mocks["twilio_client"]
    mock_twilio.messages.create.assert_called_once()
    sms_body = mock_twilio.messages.create.call_args.kwargs["body"]
    assert "Mike Torres" in sms_body
    assert "within 45 minutes" in sms_body
    assert "ST-9001" in sms_body
    assert mock_twilio.messages.create.call_args.kwargs["to"] == "+15551234567"
