# pricing-service/lookup.py

from typing import Optional

from embedder import PricingEmbedder
from fallbacks import PricingResult, get_category_fallback

EMBEDDING_MODEL = PricingEmbedder.MODEL
MIN_SIMILARITY = 0.70


async def lookup_price(
    description: str,
    category: Optional[str],
    tenant_id: str,
    is_emergency: bool,
    db_pool,
    oai_client,
    top_k: int = 3,
) -> PricingResult:
    embed_response = await oai_client.embeddings.create(
        input=description,
        model=EMBEDDING_MODEL,
    )
    query_embedding = embed_response.data[0].embedding

    category_filter = "AND service_category = $3" if category else ""
    params = [tenant_id, query_embedding]
    if category:
        params.append(category)

    rows = await db_pool.fetch(
        f"""
        SELECT
            service_name,
            service_category,
            min_price,
            max_price,
            typical_duration_hours,
            emergency_surcharge_pct,
            1 - (embedding <=> $2) AS similarity
        FROM pricing_catalog
        WHERE tenant_id = $1
          {category_filter}
          AND 1 - (embedding <=> $2) > {MIN_SIMILARITY}
        ORDER BY embedding <=> $2
        LIMIT {top_k}
    """,
        *params,
    )

    if not rows:
        return get_category_fallback(category, is_emergency)

    total_weight = sum(r["similarity"] for r in rows)
    weighted_min = sum(r["min_price"] * r["similarity"] for r in rows) / total_weight
    weighted_max = sum(r["max_price"] * r["similarity"] for r in rows) / total_weight
    avg_confidence = total_weight / len(rows)
    best_match = rows[0]

    surcharge = best_match["emergency_surcharge_pct"] / 100
    return PricingResult(
        service_name=best_match["service_name"],
        service_category=best_match["service_category"],
        min_price=round(weighted_min, -1),
        max_price=round(weighted_max, -1),
        emergency_min=round(weighted_min * (1 + surcharge), -1),
        emergency_max=round(weighted_max * (1 + surcharge), -1),
        confidence=avg_confidence,
        typical_duration_hours=best_match["typical_duration_hours"],
    )
