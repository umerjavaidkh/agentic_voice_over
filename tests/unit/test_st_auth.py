from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.service_titan_auth import ServiceTitanAuth


def _mock_httpx_client(access_token: str = "tok-abc", expires_in: int = 3600):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": access_token,
        "expires_in": expires_in,
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_get_token_fetches_and_returns_access_token():
    mock_client = _mock_httpx_client()

    with patch("adapters.service_titan_auth.httpx.AsyncClient", return_value=mock_client):
        auth = ServiceTitanAuth("client-id", "client-secret", "st-tenant-1")
        token = await auth.get_token()

    assert token == "tok-abc"
    mock_client.post.assert_awaited_once_with(
        ServiceTitanAuth.TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": "client-id",
            "client_secret": "client-secret",
        },
    )


@pytest.mark.asyncio
async def test_get_token_caches_second_call_within_expiry():
    mock_client = _mock_httpx_client()

    with patch("adapters.service_titan_auth.httpx.AsyncClient", return_value=mock_client):
        auth = ServiceTitanAuth("client-id", "client-secret", "st-tenant-1")
        first = await auth.get_token()
        second = await auth.get_token()

    assert first == "tok-abc"
    assert second == "tok-abc"
    mock_client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_token_refetches_after_expiry():
    mock_client = _mock_httpx_client()

    with patch("adapters.service_titan_auth.httpx.AsyncClient", return_value=mock_client):
        auth = ServiceTitanAuth("client-id", "client-secret", "st-tenant-1")
        await auth.get_token()
        auth._expires_at = datetime.utcnow() - timedelta(seconds=1)
        await auth.get_token()

    assert mock_client.post.await_count == 2
