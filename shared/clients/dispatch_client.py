class DispatchClient:
    """HTTP client for the dispatch-adapter service (ServiceTitan / HCP)."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    async def create_job(self, payload: dict) -> dict:
        raise NotImplementedError("DispatchClient.create_job is implemented via dispatch-adapter HTTP API")
