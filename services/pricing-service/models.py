from typing import Optional

from pydantic import BaseModel


class PricingRequest(BaseModel):
    tenant_id: str
    description: str
    category: Optional[str] = None
    is_emergency: bool = False
