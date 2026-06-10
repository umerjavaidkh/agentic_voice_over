# pricing-service/fallbacks.py

from typing import Optional

from pydantic import BaseModel

DEFAULT_SURCHARGE_PCT = 25.0


class PricingResult(BaseModel):
    service_name: str
    service_category: str
    min_price: float
    max_price: float
    emergency_min: float
    emergency_max: float
    confidence: float
    typical_duration_hours: float


def _fallback(
    category: str,
    label: str,
    min_price: float,
    max_price: float,
) -> PricingResult:
    surcharge = DEFAULT_SURCHARGE_PCT / 100
    return PricingResult(
        service_name=f"{label} service (estimated range)",
        service_category=category,
        min_price=min_price,
        max_price=max_price,
        emergency_min=round(min_price * (1 + surcharge), -1),
        emergency_max=round(max_price * (1 + surcharge), -1),
        confidence=0.0,
        typical_duration_hours=2.0,
    )


CATEGORY_FALLBACKS: dict[str, PricingResult] = {
    "plumbing": _fallback("plumbing", "Plumbing", 150, 600),
    "hvac": _fallback("hvac", "HVAC", 200, 800),
    "roofing": _fallback("roofing", "Roofing", 300, 1500),
    "electrical": _fallback("electrical", "Electrical", 150, 500),
    "general": _fallback("general", "General", 100, 500),
}


def get_category_fallback(category: Optional[str], is_emergency: bool) -> PricingResult:
    key = category if category in CATEGORY_FALLBACKS else "general"
    base = CATEGORY_FALLBACKS[key]
    if is_emergency:
        return base.model_copy()
    return base.model_copy(
        update={
            "emergency_min": base.min_price,
            "emergency_max": base.max_price,
        }
    )
