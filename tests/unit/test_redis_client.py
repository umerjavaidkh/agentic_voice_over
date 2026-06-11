import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.clients.redis_client import RedisClient


@pytest.fixture
def redis_client():
    with patch("shared.clients.redis_client.aioredis.ConnectionPool.from_url"):
        with patch("shared.clients.redis_client.aioredis.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_redis_cls.return_value = mock_redis
            client = RedisClient("redis://localhost:6379")
            client.redis = mock_redis
            yield client


@pytest.mark.asyncio
async def test_get_call_state_returns_none_when_missing(redis_client):
    redis_client.redis.get = AsyncMock(return_value=None)
    assert await redis_client.get_call_state("t_abc", "CA123") is None
    redis_client.redis.get.assert_awaited_once_with("call:t_abc:CA123")


@pytest.mark.asyncio
async def test_set_call_state_uses_tenant_namespaced_key(redis_client):
    redis_client.redis.setex = AsyncMock()
    state = {"call_sid": "CA123", "tenant_id": "t_abc"}
    await redis_client.set_call_state("t_abc", "CA123", state, ttl=1800)
    redis_client.redis.setex.assert_awaited_once_with(
        "call:t_abc:CA123",
        1800,
        json.dumps(state),
    )


@pytest.mark.asyncio
async def test_call_meta_round_trip(redis_client):
    redis_client.redis.setex = AsyncMock()
    redis_client.redis.get = AsyncMock(return_value=json.dumps({"tenant_id": "t_abc"}))
    meta = {"tenant_id": "t_abc", "room_name": "t_abc_CA123"}
    await redis_client.set_call_meta("CA123", meta)
    loaded = await redis_client.get_call_meta("CA123")
    assert loaded == {"tenant_id": "t_abc"}
    redis_client.redis.setex.assert_awaited_once_with(
        "call_meta:CA123",
        1800,
        json.dumps(meta),
    )
