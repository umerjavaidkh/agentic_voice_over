from pydantic import BaseModel

from shared.models.agent_state import ServiceCategory


class PricingResult(BaseModel):
    min_price: float
    max_price: float
    confidence: float


class PricingClient:
    """HTTP client for the pricing-service microservice."""

    async def lookup(
        self,
        *,
        description: str,
        category: ServiceCategory | None,
        tenant_id: str,
    ) -> PricingResult:
        raise NotImplementedError("PricingClient.lookup is implemented via pricing-service HTTP API")
