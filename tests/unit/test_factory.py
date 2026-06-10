from unittest.mock import AsyncMock, patch

import pytest

from adapters.housecall_pro import HousecallProAdapter
from adapters.service_titan import ServiceTitanAdapter
from factory import get_adapter


@pytest.mark.asyncio
async def test_get_adapter_returns_service_titan_adapter():
    mock_vault = AsyncMock()
    mock_vault.get_tenant_config = AsyncMock(
        return_value={
            "fsm": "servicetitan",
            "st_client_id": "st-client-id",
            "st_client_secret": "st-client-secret",
            "st_tenant_id": "st-tenant-99",
            "st_app_key": "st-app-key",
            "st_business_unit_id": "bu-7",
        }
    )

    with patch("factory.vault", mock_vault):
        adapter = await get_adapter("t_servicetitan")

    assert isinstance(adapter, ServiceTitanAdapter)
    assert adapter.st_tenant_id == "st-tenant-99"
    assert adapter.app_key == "st-app-key"
    assert adapter.business_unit_id == "bu-7"
    mock_vault.get_tenant_config.assert_awaited_once_with("t_servicetitan")


@pytest.mark.asyncio
async def test_get_adapter_returns_housecall_pro_adapter():
    mock_vault = AsyncMock()
    mock_vault.get_tenant_config = AsyncMock(
        return_value={
            "fsm": "housecall_pro",
            "hcp_api_key": "hcp-secret-key",
        }
    )

    with patch("factory.vault", mock_vault):
        adapter = await get_adapter("t_hcp")

    assert isinstance(adapter, HousecallProAdapter)
    assert adapter.api_key == "hcp-secret-key"
    mock_vault.get_tenant_config.assert_awaited_once_with("t_hcp")


@pytest.mark.asyncio
async def test_get_adapter_raises_for_unknown_fsm():
    mock_vault = AsyncMock()
    mock_vault.get_tenant_config = AsyncMock(return_value={"fsm": "jobber"})

    with patch("factory.vault", mock_vault):
        with pytest.raises(ValueError, match="Unknown FSM: jobber"):
            await get_adapter("t_unknown")
