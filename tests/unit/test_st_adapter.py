from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from adapters.service_titan import ServiceTitanAdapter
from base import JobPayload, JobResult


def _sample_payload(**overrides) -> JobPayload:
    defaults = {
        "tenant_id": "t_abc123",
        "caller_name": "Ahmed Khan",
        "caller_phone": "+15551234567",
        "address": "123 Main Street, Dubai",
        "problem": "Water heater leaking from bottom",
        "service_category": "plumbing",
        "urgency": "emergency",
        "estimate_min": 800.0,
        "estimate_max": 1800.0,
        "tech_id": "tech-99",
        "preferred_window": "next_2_hours",
    }
    defaults.update(overrides)
    return JobPayload(**defaults)


def _adapter() -> ServiceTitanAdapter:
    return ServiceTitanAdapter(
        client_id="st-client",
        client_secret="st-secret",
        st_tenant_id="st-tenant-1",
        app_key="st-app-key",
        business_unit_id="bu-1",
    )


@pytest.mark.asyncio
async def test_create_job_happy_path():
    adapter = _adapter()
    payload = _sample_payload()
    adapter.auth.get_token = AsyncMock(return_value="token-abc")

    with patch.object(adapter, "_step_create_customer", AsyncMock(return_value="cust-1")) as step1, patch.object(
        adapter, "_step_create_booking", AsyncMock(return_value=42)
    ) as step2, patch.object(
        adapter,
        "_step_confirm_dispatch",
        AsyncMock(return_value={"name": "Mike Torres", "phoneNumber": "+15559876543"}),
    ) as step3:
        result = await adapter.create_job(payload)

    assert result == JobResult(
        job_id="42",
        booking_confirmed=True,
        tech_name="Mike Torres",
        tech_phone="+15559876543",
        eta_window="next_2_hours",
        confirmation_number="ST-42",
    )
    step1.assert_awaited_once()
    step2.assert_awaited_once()
    step3.assert_awaited_once()
    step2.assert_awaited_with(
        step1.await_args.args[0],
        step1.await_args.args[1],
        step1.await_args.args[2],
        payload,
        "cust-1",
    )
    step3.assert_awaited_with(
        step1.await_args.args[0],
        step1.await_args.args[1],
        step1.await_args.args[2],
        42,
        "tech-99",
    )


@pytest.mark.asyncio
async def test_create_job_raises_on_step_2_503():
    adapter = _adapter()
    payload = _sample_payload()
    adapter.auth.get_token = AsyncMock(return_value="token-abc")

    response = MagicMock()
    response.status_code = 503
    error = httpx.HTTPStatusError(
        "Service Unavailable",
        request=MagicMock(),
        response=response,
    )

    with patch.object(adapter, "_step_create_customer", AsyncMock(return_value="cust-1")), patch.object(
        adapter, "_step_create_booking", AsyncMock(side_effect=error)
    ) as step2, patch.object(adapter, "_step_confirm_dispatch", AsyncMock()) as step3:
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await adapter.create_job(payload)

    assert exc_info.value.response.status_code == 503
    step2.assert_awaited_once()
    step3.assert_not_awaited()


@pytest.mark.asyncio
async def test_step_create_customer_posts_to_crm_endpoint():
    adapter = _adapter()
    payload = _sample_payload()

    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "cust-77"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    customer_id = await adapter._step_create_customer(
        mock_client,
        adapter._auth_headers("token"),
        adapter.BASE_URL.format(tenant_id=adapter.st_tenant_id),
        payload,
    )

    assert customer_id == "cust-77"
    mock_client.post.assert_awaited_once()
    call_kwargs = mock_client.post.await_args.kwargs
    assert call_kwargs["json"]["name"] == "Ahmed Khan"
    assert call_kwargs["json"]["address"]["city"] == "Dubai"
