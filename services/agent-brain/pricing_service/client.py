import os

import httpx
from pydantic import BaseModel

from shared.models.agent_state import ServiceCategory


class PricingResult(BaseModel):
    min_price: float
    max_price: float
    confidence: float


class PricingClient:
    """HTTP client for the pricing-service microservice."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (
            base_url or os.getenv("PRICING_SERVICE_URL", "http://pricing-service:8002")
        ).rstrip("/")

    async def lookup(
        self,
        *,
        description: str,
        category: ServiceCategory | None,
        tenant_id: str,
        is_emergency: bool = False,
    ) -> PricingResult:
        category_value = category.value if category else None
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/pricing/lookup",
                json={
                    "tenant_id": tenant_id,
                    "description": description,
                    "category": category_value,
                    "is_emergency": is_emergency,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        return PricingResult(
            min_price=data["min_price"],
            max_price=data["max_price"],
            confidence=data["confidence"],
        )
