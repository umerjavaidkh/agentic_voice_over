# shared/clients/redis_client.py

import json
from typing import Optional

import redis.asyncio as aioredis


class RedisClient:
    def __init__(self, url: str):
        self.pool = aioredis.ConnectionPool.from_url(url, max_connections=50)
        self.redis = aioredis.Redis(connection_pool=self.pool)

    async def get_call_state(self, tenant_id: str, call_sid: str) -> Optional[dict]:
        key = f"call:{tenant_id}:{call_sid}"
        data = await self.redis.get(key)
        return json.loads(data) if data else None

    async def set_call_state(self, tenant_id: str, call_sid: str, state: dict, ttl: int = 1800):
        key = f"call:{tenant_id}:{call_sid}"
        await self.redis.setex(key, ttl, json.dumps(state))

    async def delete_call_state(self, tenant_id: str, call_sid: str):
        await self.redis.delete(f"call:{tenant_id}:{call_sid}")

    async def set_call_meta(self, call_sid: str, meta: dict, ttl: int = 1800):
        await self.redis.setex(f"call_meta:{call_sid}", ttl, json.dumps(meta))

    async def get_call_meta(self, call_sid: str) -> Optional[dict]:
        data = await self.redis.get(f"call_meta:{call_sid}")
        return json.loads(data) if data else None

    async def get_pricing_cache(self, description_hash: str) -> Optional[dict]:
        data = await self.redis.get(f"pricing_cache:{description_hash}")
        return json.loads(data) if data else None

    async def set_pricing_cache(self, description_hash: str, result: dict, ttl: int = 3600):
        await self.redis.setex(f"pricing_cache:{description_hash}", ttl, json.dumps(result))

    async def close(self):
        await self.redis.aclose()
        await self.pool.aclose()
