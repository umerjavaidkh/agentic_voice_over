from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.models.agent_state import AgentState, ServiceCategory, Technician


def _base_state(**kwargs) -> AgentState:
    defaults = {
        "call_sid": "CA123",
        "tenant_id": "t_abc",
        "caller_phone": "+15551234567",
        "problem_description": "Water heater leaking",
        "service_category": ServiceCategory.PLUMBING,
        "address": "123 Main Street, Dubai",
    }
    defaults.update(kwargs)
    return AgentState(**defaults)


@pytest.mark.asyncio
async def test_run_pricing_tool_returns_unchanged_when_problem_missing():
    state = _base_state(problem_description=None)

    with patch("pricing_service.client.PricingClient") as mock_client_cls:
        from tools.pricing_tool import run_pricing_tool

        result = await run_pricing_tool(state)

    mock_client_cls.assert_not_called()
    assert result == {}


@pytest.mark.asyncio
async def test_run_pricing_tool_updates_estimates():
    state = _base_state()

    mock_result = MagicMock()
    mock_result.min_price = 200.0
    mock_result.max_price = 450.0
    mock_result.confidence = 0.92

    mock_client = MagicMock()
    mock_client.lookup = AsyncMock(return_value=mock_result)

    with patch("pricing_service.client.PricingClient", return_value=mock_client):
        from tools.pricing_tool import run_pricing_tool

        result = await run_pricing_tool(state)

    mock_client.lookup.assert_awaited_once_with(
        description="Water heater leaking",
        category=ServiceCategory.PLUMBING,
        tenant_id="t_abc",
    )
    assert result == {
        "estimate_min": 200.0,
        "estimate_max": 450.0,
        "pricing_confidence": 0.92,
    }


@pytest.mark.asyncio
async def test_run_geo_tool_returns_unchanged_when_address_missing():
    state = _base_state(address=None)

    with patch("tools.geo_tool.find_nearest_technician", new_callable=AsyncMock) as mock_geo:
        from tools.geo_tool import run_geo_tool

        result = await run_geo_tool(state)

    mock_geo.assert_not_awaited()
    assert result == {}


@pytest.mark.asyncio
async def test_run_geo_tool_assigns_technician_emergency():
    state = _base_state(is_emergency=True)

    tech = Technician(
        tech_id="tech_1",
        name="Mike",
        phone="+15559876543",
        distance_km=4.2,
        eta_minutes=45,
        specialty=ServiceCategory.PLUMBING,
    )

    with patch("tools.geo_tool.find_nearest_technician", new_callable=AsyncMock, return_value=tech):
        from tools.geo_tool import run_geo_tool

        result = await run_geo_tool(state)

    assert result == {
        "assigned_technician": tech,
        "dispatch_eta": "within 45 minutes",
    }


@pytest.mark.asyncio
async def test_run_geo_tool_assigns_technician_scheduled():
    state = _base_state(is_emergency=False)

    tech = Technician(
        tech_id="tech_2",
        name="Sara",
        phone="+15551112222",
        distance_km=8.0,
        eta_minutes=120,
        specialty=ServiceCategory.PLUMBING,
    )

    with patch("tools.geo_tool.find_nearest_technician", new_callable=AsyncMock, return_value=tech):
        from tools.geo_tool import run_geo_tool

        result = await run_geo_tool(state)

    assert result == {
        "assigned_technician": tech,
        "dispatch_eta": "during your scheduled window",
    }
