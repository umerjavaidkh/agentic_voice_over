# pricing-service/embedder.py

import asyncio

from openai import AsyncOpenAI


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
                await conn.execute(
                    """
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
