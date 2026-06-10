from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.models.agent_state import AgentState, ServiceCategory, Technician, UrgencyLevel


def _make_state() -> AgentState:
    return AgentState(
        call_sid="CA123",
        tenant_id="t_abc",
        caller_phone="+15551234567",
        caller_name="Ahmed",
        address="123 Main Street, Dubai",
        problem_description="Water heater leaking",
        service_category=ServiceCategory.PLUMBING,
        urgency_level=UrgencyLevel.EMERGENCY,
        estimate_min=200.0,
        estimate_max=450.0,
        dispatch_eta="within 45 minutes",
        assigned_technician=Technician(
            tech_id="tech_1",
            name="Mike",
            phone="+15559876543",
            distance_km=4.2,
            eta_minutes=45,
            specialty=ServiceCategory.PLUMBING,
        ),
    )


@pytest.mark.asyncio
async def test_dispatcher_node_success_sets_booking_confirmed():
    state = _make_state()

    mock_client = MagicMock()
    mock_client.create_job = AsyncMock(
        return_value={
            "job_id": "JOB-98765",
            "booking_confirmed": True,
            "confirmation_number": "JOB-98765",
            "business_name": "Dallas Plumbing Co.",
        }
    )

    with (
        patch("nodes.dispatcher_node.DispatchClient", return_value=mock_client),
        patch("sms.Client", return_value=MagicMock()),
        patch("sms.TWILIO_SID", "AC-test-sid"),
        patch("sms.TWILIO_TOKEN", "test-token"),
        patch("sms.TWILIO_FROM_NUMBER", "+12145550001"),
    ):
        from nodes.dispatcher_node import dispatcher_node

        result = await dispatcher_node(state)

    mock_client.create_job.assert_awaited_once_with({
        "caller_name": "Ahmed",
        "caller_phone": "+15551234567",
        "address": "123 Main Street, Dubai",
        "problem": "Water heater leaking",
        "service_category": ServiceCategory.PLUMBING,
        "urgency": UrgencyLevel.EMERGENCY,
        "estimate_min": 200.0,
        "estimate_max": 450.0,
        "tech_id": "tech_1",
        "business_name": "Dallas Plumbing Co.",
    })
    assert result.job_id == "JOB-98765"
    assert result.booking_confirmed is True
    assert result.fallback_triggered is False
    assert "You're all set, Ahmed" in result.agent_response
    assert "Mike" in result.agent_response
    assert "within 45 minutes" in result.agent_response
    assert "+15551234567" in result.agent_response


@pytest.mark.asyncio
async def test_dispatcher_node_failure_sets_fallback():
    state = _make_state()

    mock_client = MagicMock()
    mock_client.create_job = AsyncMock(side_effect=RuntimeError("FSM API unavailable"))

    with patch("nodes.dispatcher_node.DispatchClient", return_value=mock_client):
        from nodes.dispatcher_node import dispatcher_node

        result = await dispatcher_node(state)

    assert result.booking_confirmed is False
    assert result.job_id is None
    assert result.fallback_triggered is True
    assert result.error_message == "FSM API unavailable"
    assert "having trouble completing the booking" in result.agent_response
