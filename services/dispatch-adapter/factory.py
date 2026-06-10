# services/dispatch-adapter/factory.py

from adapters.housecall_pro import HousecallProAdapter
from adapters.service_titan import ServiceTitanAdapter
from base import DispatchAdapterBase
from shared.clients.vault import AzureKeyVaultClient

vault = AzureKeyVaultClient()


async def get_adapter(tenant_id: str) -> DispatchAdapterBase:
    config = await vault.get_tenant_config(tenant_id)

    if config["fsm"] == "servicetitan":
        return ServiceTitanAdapter(
            client_id=config["st_client_id"],
            client_secret=config["st_client_secret"],
            st_tenant_id=config["st_tenant_id"],
            app_key=config["st_app_key"],
            business_unit_id=config["st_business_unit_id"],
        )
    if config["fsm"] == "housecall_pro":
        return HousecallProAdapter(api_key=config["hcp_api_key"])
    raise ValueError(f"Unknown FSM: {config['fsm']}")
