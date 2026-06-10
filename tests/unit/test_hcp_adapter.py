from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from adapters.housecall_pro import HousecallProAdapter
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
        "tech_id": "emp-42",
        "preferred_window": "next_2_hours",
        "notes": "Caller is home now",
    }
    defaults.update(overrides)
    return JobPayload(**defaults)


def _adapter() -> HousecallProAdapter:
    return HousecallProAdapter(api_key="hcp-test-key")


def _mock_jobs_client(job_response: dict):
    mock_response = MagicMock()
    mock_response.json.return_value = job_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_create_job_happy_path_single_api_call():
    adapter = _adapter()
    payload = _sample_payload()
    mock_client = _mock_jobs_client(
        {
            "id": "job-hcp-9001",
            "assigned_employees": [{"name": "Sarah Tech"}],
        }
    )

    with patch("adapters.housecall_pro.httpx.AsyncClient", return_value=mock_client):
        result = await adapter.create_job(payload)

    assert result == JobResult(
        job_id="job-hcp-9001",
        booking_confirmed=True,
        tech_name="Sarah Tech",
        tech_phone="",
        eta_window="next_2_hours",
        confirmation_number="HCP-job-hcp-9001",
    )
    mock_client.post.assert_awaited_once()
    call_args = mock_client.post.await_args
    assert call_args.args[0] == f"{HousecallProAdapter.BASE_URL}/jobs"
    assert call_args.kwargs["headers"]["Authorization"] == "Token hcp-test-key"


@pytest.mark.asyncio
async def test_create_job_combines_customer_and_job_in_one_request():
    adapter = _adapter()
    payload = _sample_payload()

    mock_client = _mock_jobs_client({"id": "job-1", "assigned_employees": []})

    with patch("adapters.housecall_pro.httpx.AsyncClient", return_value=mock_client):
        await adapter.create_job(payload)

    body = mock_client.post.await_args.kwargs["json"]
    assert body["customer"] == {
        "first_name": "Ahmed",
        "last_name": "Khan",
        "mobile_number": "+15551234567",
    }
    assert body["address"]["street"] == "123 Main Street, Dubai"
    assert body["line_items"][0]["name"] == payload.problem
    assert body["line_items"][0]["description"] == "AI Estimate: $800–$1800"
    assert body["line_items"][0]["unit_price"] == 800.0
    assert body["assigned_employee_ids"] == ["emp-42"]
    assert body["tags"] == ["emergency", "ai_booked"]
    assert body["private_notes"] == "Booked via AI voice agent. Caller is home now"
    assert "scheduled_start" in body
    assert "scheduled_end" in body


@pytest.mark.asyncio
async def test_create_job_single_name_splits_correctly():
    adapter = _adapter()
    payload = _sample_payload(caller_name="Madonna")

    mock_client = _mock_jobs_client({"id": "job-2", "assigned_employees": []})

    with patch("adapters.housecall_pro.httpx.AsyncClient", return_value=mock_client):
        await adapter.create_job(payload)

    customer = mock_client.post.await_args.kwargs["json"]["customer"]
    assert customer["first_name"] == "Madonna"
    assert customer["last_name"] == ""


@pytest.mark.asyncio
async def test_create_job_raises_on_http_error():
    adapter = _adapter()
    payload = _sample_payload()

    response = MagicMock()
    response.status_code = 422
    error = httpx.HTTPStatusError("Unprocessable", request=MagicMock(), response=response)

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = error

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("adapters.housecall_pro.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.create_job(payload)

    mock_client.post.assert_awaited_once()
