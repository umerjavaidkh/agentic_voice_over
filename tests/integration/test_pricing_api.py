import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fallbacks import PricingResult


LOOKUP_RESULT = PricingResult(
    service_name="Water heater replacement",
    service_category="plumbing",
    min_price=800,
    max_price=1800,
    emergency_min=1000,
    emergency_max=2250,
    confidence=0.87,
    typical_duration_hours=3.0,
)

LOOKUP_REQUEST = {
    "tenant_id": "t_abc123",
    "description": "water heater making loud rumbling noise and leaking from bottom",
    "category": "plumbing",
    "is_emergency": True,
}


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = value

    async def aclose(self):
        return None


@pytest.fixture
def pricing_client(monkeypatch):
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://devuser:devpass@localhost:5432/voice_agent_dev")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    fake_redis = FakeRedis()
    mock_pool = MagicMock()
    mock_pool.close = AsyncMock()

    async def fake_create_pool(*args, **kwargs):
        return mock_pool

    mock_lookup = AsyncMock(return_value=LOOKUP_RESULT)

    import config
    import main

    importlib.reload(config)
    with patch("main.asyncpg.create_pool", side_effect=fake_create_pool):
        with patch("main.redis.from_url", return_value=fake_redis):
            with patch("main.AsyncOpenAI", return_value=MagicMock()):
                importlib.reload(main)
                with patch.object(main, "lookup_price", mock_lookup):
                    with TestClient(main.app) as client:
                        client.fake_redis = fake_redis
                        client.mock_lookup = mock_lookup
                        yield client


def test_pricing_lookup_returns_result(pricing_client):
    response = pricing_client.post("/pricing/lookup", json=LOOKUP_REQUEST)

    assert response.status_code == 200
    assert response.json() == LOOKUP_RESULT.model_dump()
    pricing_client.mock_lookup.assert_awaited_once()


def test_pricing_lookup_cache_hit_skips_pgvector_lookup(pricing_client):
    first = pricing_client.post("/pricing/lookup", json=LOOKUP_REQUEST)
    second = pricing_client.post("/pricing/lookup", json=LOOKUP_REQUEST)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == LOOKUP_RESULT.model_dump()
    pricing_client.mock_lookup.assert_awaited_once()
    assert len(pricing_client.fake_redis.store) == 1


def test_health_endpoint(pricing_client):
    response = pricing_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "pricing-service"}
