import hashlib
import logging
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as redis
from fastapi import Depends, FastAPI, Request
from openai import AsyncOpenAI

from config import settings
from fallbacks import PricingResult
from lookup import lookup_price
from models import PricingRequest

logger = logging.getLogger(__name__)


def description_cache_key(
    tenant_id: str,
    category: str | None,
    is_emergency: bool,
    description: str,
) -> str:
    digest = hashlib.md5(description.encode("utf-8")).hexdigest()
    category_part = category or "_"
    return f"pricing:lookup:{tenant_id}:{category_part}:{is_emergency}:{digest}"


async def get_db_pool(request: Request):
    return request.app.state.db_pool


async def get_oai_client(request: Request):
    return request.app.state.oai_client


async def get_redis(request: Request):
    return request.app.state.redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await asyncpg.create_pool(settings.postgres_dsn)
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    app.state.oai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    yield
    await app.state.db_pool.close()
    await app.state.redis.aclose()


app = FastAPI(title="pricing-service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "pricing-service"}


@app.post("/pricing/lookup", response_model=PricingResult)
async def price_lookup(
    req: PricingRequest,
    db=Depends(get_db_pool),
    oai=Depends(get_oai_client),
    redis_client=Depends(get_redis),
):
    cache_key = description_cache_key(
        req.tenant_id,
        req.category,
        req.is_emergency,
        req.description,
    )

    cached = await redis_client.get(cache_key)
    if cached:
        logger.debug("pricing cache hit", extra={"cache_key": cache_key})
        return PricingResult.model_validate_json(cached)

    result = await lookup_price(
        description=req.description,
        category=req.category,
        tenant_id=req.tenant_id,
        is_emergency=req.is_emergency,
        db_pool=db,
        oai_client=oai,
    )

    await redis_client.set(
        cache_key,
        result.model_dump_json(),
        ex=settings.pricing_cache_ttl_seconds,
    )
    return result
