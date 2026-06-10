# 04 — Pricing Engine Plan

**Service:** `pricing-service`  
**Stack:** pgvector · OpenAI Embeddings · FastAPI  
**Target Latency:** < 80ms per lookup  

---

## 1. Core Concept

The pricing engine answers one question:
> "Given this caller's problem description, what is the likely cost range?"

It does this via **semantic similarity** — not keyword matching, not a hardcoded price list.

A "water heater thermocouple replacement" query will match "water heater pilot light issue" because the embeddings are semantically close, even though the words differ.

---

## 2. Data Model

### 2.1 Price Catalog Entry

```sql
-- migrations/001_pricing_catalog.sql

CREATE TABLE pricing_catalog (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    service_name    TEXT NOT NULL,         -- "Water heater thermocouple replacement"
    service_category TEXT NOT NULL,        -- "plumbing"
    description     TEXT NOT NULL,         -- Full description used for embedding
    min_price       DECIMAL(10,2) NOT NULL,
    max_price       DECIMAL(10,2) NOT NULL,
    unit            TEXT DEFAULT 'job',    -- 'job', 'hour', 'sqft'
    typical_duration_hours DECIMAL(4,2),
    is_emergency_eligible BOOLEAN DEFAULT true,
    emergency_surcharge_pct DECIMAL(5,2) DEFAULT 25.0,
    embedding       vector(1536),          -- OpenAI text-embedding-3-small
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast ANN search
CREATE INDEX pricing_catalog_embedding_idx
    ON pricing_catalog
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Tenant filter index
CREATE INDEX pricing_catalog_tenant_idx
    ON pricing_catalog (tenant_id, service_category);
```

### 2.2 Sample Data

```python
# pricing-service/seed_data.py

CATALOG_SEED = [
    # PLUMBING
    {
        "service_name": "Water heater replacement",
        "service_category": "plumbing",
        "description": "Full water heater unit replacement including removal of old unit, installation of new unit, connection to gas or electric supply, and testing",
        "min_price": 800,
        "max_price": 1800,
        "typical_duration_hours": 3.0,
    },
    {
        "service_name": "Water heater thermocouple replacement",
        "service_category": "plumbing",
        "description": "Replace faulty thermocouple or thermopile on gas water heater, pilot light won't stay lit, burner not igniting",
        "min_price": 120,
        "max_price": 250,
        "typical_duration_hours": 1.0,
    },
    {
        "service_name": "Emergency pipe burst repair",
        "service_category": "plumbing",
        "description": "Emergency repair of burst pipe, active leak, flooding, water damage prevention, shut off and repair",
        "min_price": 300,
        "max_price": 800,
        "typical_duration_hours": 2.0,
    },
    {
        "service_name": "Drain cleaning",
        "service_category": "plumbing",
        "description": "Clear blocked or slow drain, kitchen sink, bathroom sink, shower drain, main line cleaning",
        "min_price": 100,
        "max_price": 350,
        "typical_duration_hours": 1.5,
    },
    # HVAC
    {
        "service_name": "AC unit not cooling repair",
        "service_category": "hvac",
        "description": "Diagnose and repair air conditioner not producing cold air, refrigerant check, compressor inspection, thermostat check",
        "min_price": 150,
        "max_price": 600,
        "typical_duration_hours": 2.0,
    },
    {
        "service_name": "Furnace repair",
        "service_category": "hvac",
        "description": "Diagnose and repair gas or electric furnace not heating, no heat, blower issues, ignitor replacement",
        "min_price": 200,
        "max_price": 700,
        "typical_duration_hours": 2.5,
    },
    # ROOFING
    {
        "service_name": "Emergency roof leak repair",
        "service_category": "roofing",
        "description": "Emergency repair of active roof leak, tarping, shingle replacement, flashing repair, storm damage",
        "min_price": 400,
        "max_price": 1500,
        "typical_duration_hours": 4.0,
    },
]
```

---

## 3. Embedding Pipeline

### 3.1 Ingestion (one-time + incremental)

```python
# pricing-service/embedder.py

from openai import AsyncOpenAI
import asyncio

class PricingEmbedder:
    MODEL = "text-embedding-3-small"  # 1536 dims, cost-efficient

    def __init__(self, db_pool, openai_client):
        self.db = db_pool
        self.oai = openai_client

    def build_embed_text(self, entry: dict) -> str:
        """
        Combine fields for richer semantic matching.
        Do NOT embed price — it would bias similarity.
        """
        return (
            f"{entry['service_name']}. "
            f"Category: {entry['service_category']}. "
            f"{entry['description']}"
        )

    async def embed_catalog_entry(self, entry: dict) -> list[float]:
        text = self.build_embed_text(entry)
        response = await self.oai.embeddings.create(
            input=text,
            model=self.MODEL,
        )
        return response.data[0].embedding

    async def seed_tenant_catalog(self, tenant_id: str, entries: list[dict]):
        """Batch embed and insert all entries for a tenant."""
        tasks = [self.embed_catalog_entry(e) for e in entries]
        embeddings = await asyncio.gather(*tasks)

        async with self.db.acquire() as conn:
            for entry, embedding in zip(entries, embeddings):
                await conn.execute("""
                    INSERT INTO pricing_catalog
                    (tenant_id, service_name, service_category, description,
                     min_price, max_price, typical_duration_hours, embedding)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    ON CONFLICT DO NOTHING
                """,
                    tenant_id,
                    entry["service_name"],
                    entry["service_category"],
                    entry["description"],
                    entry["min_price"],
                    entry["max_price"],
                    entry.get("typical_duration_hours", 2.0),
                    embedding,
                )
```

---

## 4. Lookup API

### 4.1 Query Logic

```python
# pricing-service/lookup.py

from pydantic import BaseModel
from typing import Optional

class PricingResult(BaseModel):
    service_name: str
    service_category: str
    min_price: float
    max_price: float
    emergency_min: float
    emergency_max: float
    confidence: float         # cosine similarity score (0–1)
    typical_duration_hours: float

async def lookup_price(
    description: str,
    category: Optional[str],
    tenant_id: str,
    is_emergency: bool,
    db_pool,
    oai_client,
    top_k: int = 3,
) -> PricingResult:
    # 1. Embed the caller's description
    embed_response = await oai_client.embeddings.create(
        input=description,
        model="text-embedding-3-small",
    )
    query_embedding = embed_response.data[0].embedding

    # 2. Vector search with tenant + category filter
    category_filter = "AND service_category = $3" if category else ""
    params = [tenant_id, query_embedding]
    if category:
        params.append(category)

    rows = await db_pool.fetch(f"""
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
          AND 1 - (embedding <=> $2) > 0.70    -- minimum confidence
        ORDER BY embedding <=> $2
        LIMIT {top_k}
    """, *params)

    if not rows:
        # Fallback to category-level wide bands
        return get_category_fallback(category, is_emergency)

    # 3. Weighted average of top-k results (similarity-weighted)
    total_weight = sum(r["similarity"] for r in rows)
    weighted_min = sum(r["min_price"] * r["similarity"] for r in rows) / total_weight
    weighted_max = sum(r["max_price"] * r["similarity"] for r in rows) / total_weight
    avg_confidence = total_weight / len(rows)
    best_match = rows[0]

    surcharge = best_match["emergency_surcharge_pct"] / 100
    return PricingResult(
        service_name=best_match["service_name"],
        service_category=best_match["service_category"],
        min_price=round(weighted_min, -1),        # round to nearest $10
        max_price=round(weighted_max, -1),
        emergency_min=round(weighted_min * (1 + surcharge), -1),
        emergency_max=round(weighted_max * (1 + surcharge), -1),
        confidence=avg_confidence,
        typical_duration_hours=best_match["typical_duration_hours"],
    )
```

### 4.2 Category Fallback (when no match > 70%)

```python
CATEGORY_FALLBACKS = {
    "plumbing":   PricingResult(min_price=150, max_price=600,  confidence=0.0, ...),
    "hvac":       PricingResult(min_price=200, max_price=800,  confidence=0.0, ...),
    "roofing":    PricingResult(min_price=300, max_price=1500, confidence=0.0, ...),
    "electrical": PricingResult(min_price=150, max_price=500,  confidence=0.0, ...),
    "general":    PricingResult(min_price=100, max_price=500,  confidence=0.0, ...),
}
```

---

## 5. FastAPI Endpoint

```python
# pricing-service/main.py

from fastapi import FastAPI, Depends
from .lookup import lookup_price
from .models import PricingRequest, PricingResult

app = FastAPI()

@app.post("/pricing/lookup", response_model=PricingResult)
async def price_lookup(
    req: PricingRequest,
    db=Depends(get_db_pool),
    oai=Depends(get_oai_client),
):
    return await lookup_price(
        description=req.description,
        category=req.category,
        tenant_id=req.tenant_id,
        is_emergency=req.is_emergency,
        db_pool=db,
        oai_client=oai,
    )
```

**Request:**
```json
{
  "tenant_id": "t_abc123",
  "description": "water heater making loud rumbling noise and leaking from bottom",
  "category": "plumbing",
  "is_emergency": true
}
```

**Response:**
```json
{
  "service_name": "Water heater replacement",
  "service_category": "plumbing",
  "min_price": 800,
  "max_price": 1800,
  "emergency_min": 1000,
  "emergency_max": 2250,
  "confidence": 0.87,
  "typical_duration_hours": 3.0
}
```

---

## 6. Catalog Management (Admin)

For each tenant, business owners can:
- Upload custom pricing CSV via admin UI
- AI auto-generates descriptions for embedding
- Manual override for specific services

```python
# pricing-service/admin.py

@app.post("/pricing/catalog/upload")
async def upload_catalog(tenant_id: str, file: UploadFile):
    """Accept CSV: service_name, category, min_price, max_price"""
    df = pd.read_csv(file.file)
    entries = df.to_dict("records")
    
    # Auto-generate descriptions if missing
    for entry in entries:
        if "description" not in entry or not entry["description"]:
            entry["description"] = await generate_description(entry)
    
    await embedder.seed_tenant_catalog(tenant_id, entries)
    return {"status": "ok", "entries_added": len(entries)}
```

---

## 7. Performance Targets

| Metric | Target |
|--------|--------|
| p50 lookup latency | < 40ms |
| p95 lookup latency | < 80ms |
| Embedding generation | < 50ms (OpenAI API) |
| Catalog size per tenant | 50–500 entries |
| ANN index rebuild | Every 24h or on new entry |
| Cache hit rate (Redis) | > 60% (common descriptions) |

**Caching strategy:** Hash the description → check Redis first. Common queries ("water heater not working") will hit cache after the first caller.

---

## Next: [05_FSM_Integrations.Plan.md](./05_FSM_Integrations.Plan.md)
