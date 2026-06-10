-- migrations/002_pricing_catalog.sql
-- pricing_catalog table from docs/04_Pricing_Engine.Plan.md section 2.1

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
