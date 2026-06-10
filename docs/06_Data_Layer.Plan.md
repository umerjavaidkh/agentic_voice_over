# 06 — Data Layer Plan

**Stores:** Postgres + pgvector · Redis · Azure Blob Storage  
**ORM:** asyncpg (raw SQL, no ORM overhead)  
**Migration tool:** Alembic  

---

## 1. Postgres Schema

### 1.1 Tenants

```sql
CREATE TABLE tenants (
    id              TEXT PRIMARY KEY,              -- "t_abc123"
    business_name   TEXT NOT NULL,
    phone_number    TEXT NOT NULL,                 -- their Twilio number
    timezone        TEXT DEFAULT 'UTC',
    fsm_type        TEXT NOT NULL,                 -- 'servicetitan' | 'housecall_pro'
    service_categories TEXT[] DEFAULT '{}',
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### 1.2 Calls (Lead Capture)

```sql
CREATE TABLE calls (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_sid        TEXT UNIQUE NOT NULL,           -- Twilio call SID
    tenant_id       TEXT NOT NULL REFERENCES tenants(id),
    caller_phone    TEXT NOT NULL,
    caller_name     TEXT,
    address         TEXT,

    -- Problem details
    problem_description TEXT,
    service_category    TEXT,
    appliance_type      TEXT,
    urgency_level       TEXT,                       -- 'emergency'|'urgent'|'normal'

    -- Pricing
    estimate_min    DECIMAL(10,2),
    estimate_max    DECIMAL(10,2),
    pricing_confidence DECIMAL(4,3),

    -- Outcome
    call_outcome    TEXT DEFAULT 'in_progress',    -- 'booked'|'missed'|'fallback'|'abandoned'
    job_id          TEXT,                          -- FSM job ID if booked
    tech_name       TEXT,
    booking_confirmed BOOLEAN DEFAULT false,
    fallback_triggered BOOLEAN DEFAULT false,
    human_handoff   BOOLEAN DEFAULT false,

    -- Metrics
    duration_seconds    INT,
    turn_count          INT DEFAULT 0,
    recording_blob_path TEXT,

    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX calls_tenant_idx ON calls (tenant_id, created_at DESC);
CREATE INDEX calls_outcome_idx ON calls (tenant_id, call_outcome);
```

### 1.3 Conversation Turns (for analytics + retraining)

```sql
CREATE TABLE conversation_turns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id         UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    turn_number     INT NOT NULL,
    role            TEXT NOT NULL,                 -- 'user' | 'agent'
    content         TEXT NOT NULL,
    node_name       TEXT,                          -- which LangGraph node produced this
    latency_ms      INT,
    token_count     INT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX turns_call_idx ON conversation_turns (call_id, turn_number);
```

### 1.4 Technicians (Local cache of FSM data, synced hourly)

```sql
CREATE TABLE technicians (
    id              TEXT NOT NULL,                  -- FSM tech ID
    tenant_id       TEXT NOT NULL REFERENCES tenants(id),
    name            TEXT NOT NULL,
    phone           TEXT,
    email           TEXT,
    specialties     TEXT[] DEFAULT '{}',
    is_active       BOOLEAN DEFAULT true,
    current_lat     DECIMAL(10,8),
    current_lng     DECIMAL(11,8),
    last_location_update TIMESTAMPTZ,
    synced_at       TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, tenant_id)
);

CREATE INDEX technicians_tenant_idx ON technicians (tenant_id, is_active);
```

### 1.5 pricing_catalog — see [04_Pricing_Engine.Plan.md](./04_Pricing_Engine.Plan.md)

---

## 2. Redis Schema

All keys namespaced by tenant + call SID. TTL: 30 minutes (call session).

```
call:{tenant_id}:{call_sid}         → AgentState (JSON, full LangGraph state)
call_meta:{call_sid}                → {tenant_id, start_time, room_name}
pricing_cache:{hash(description)}   → PricingResult (JSON, TTL: 1 hour)
tech_locations:{tenant_id}          → {tech_id: {lat, lng, available}} (TTL: 5 min)
tenant_config:{tenant_id}           → Tenant config (TTL: 15 min, reduce Key Vault calls)
```

### Redis client setup

```python
# shared/clients/redis_client.py

import redis.asyncio as aioredis
import json
from typing import Optional

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

    async def get_pricing_cache(self, description_hash: str) -> Optional[dict]:
        data = await self.redis.get(f"pricing_cache:{description_hash}")
        return json.loads(data) if data else None

    async def set_pricing_cache(self, description_hash: str, result: dict, ttl: int = 3600):
        await self.redis.setex(f"pricing_cache:{description_hash}", ttl, json.dumps(result))
```

---

## 3. Azure Blob Storage Structure (Call Recordings & Logs)

> **Azure-only stack:** Azure Blob Storage replaces AWS S3 entirely. Same concepts — containers instead of buckets, blobs instead of objects — but fully integrated with Azure RBAC, Azure Monitor, and Key Vault.

**SDK mapping:**

| AWS (old) | Azure (current) |
|-----------|----------------|
| `boto3` | `azure-storage-blob` |
| S3 Bucket | Storage Account → Container |
| S3 Object | Blob |
| `s3.put_object()` | `blob_client.upload_blob()` |
| S3 Lifecycle Policy | Blob Lifecycle Management Policy |
| AWS KMS encryption | Azure Storage Service Encryption (SSE, on by default) |

```
Azure Storage Account: voiceagentstore{env}
├── Container: recordings
│   └── {tenant_id}/
│       └── {year}/{month}/{day}/
│           └── {call_sid}.mp3          ← dual-channel, AES-256 encrypted
│
├── Container: transcripts
│   └── {tenant_id}/
│       └── {year}/{month}/{day}/
│           └── {call_sid}.json         ← full conversation JSON
│
└── Container: agent-events
    └── {date}/
        └── {hour}/
            └── events-{partition}.json ← LangGraph turn events (retraining data)
```

**Retention Policy (via Azure Blob Lifecycle Management — same concept as S3 lifecycle rules):**
- recordings: delete after 90 days
- transcripts: delete after 1 year
- agent-events: delete after 2 years

### Upload on call end

```python
# services/voice-gateway/call_finisher.py

from azure.storage.blob.aio import BlobServiceClient
from azure.identity.aio import ManagedIdentityCredential
import os

STORAGE_ACCOUNT_URL = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
# e.g. "https://voiceagentstore.blob.core.windows.net"

async def finalize_call(call_sid: str, tenant_id: str, recording_bytes: bytes):
    # Use Managed Identity — no storage keys in code
    credential = ManagedIdentityCredential()
    blob_service = BlobServiceClient(
        account_url=STORAGE_ACCOUNT_URL,
        credential=credential,
    )

    blob_name = f"{tenant_id}/{date_path()}/{call_sid}.mp3"
    container_client = blob_service.get_container_client("recordings")

    await container_client.upload_blob(
        name=blob_name,
        data=recording_bytes,
        content_settings=ContentSettings(content_type="audio/mpeg"),
        metadata={
            "call_sid": call_sid,
            "tenant_id": tenant_id,
        },
        overwrite=False,
    )

    # Update call record with blob path
    await db.execute(
        "UPDATE calls SET recording_blob_path=$1 WHERE call_sid=$2",
        blob_name, call_sid
    )
    await blob_service.close()
```

### Lifecycle Policy (Terraform — replaces S3 lifecycle)

```hcl
# infra/terraform/blob_lifecycle.tf

resource "azurerm_storage_management_policy" "lifecycle" {
  storage_account_id = azurerm_storage_account.main.id

  rule {
    name    = "delete-recordings-90d"
    enabled = true
    filters {
      prefix_match = ["recordings/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = 90
      }
    }
  }

  rule {
    name    = "delete-transcripts-365d"
    enabled = true
    filters {
      prefix_match = ["transcripts/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = 365
      }
    }
  }

  rule {
    name    = "delete-events-730d"
    enabled = true
    filters {
      prefix_match = ["agent-events/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = 730
      }
    }
  }
}
```

### Terraform Storage Account Resource

```hcl
# infra/terraform/storage.tf

resource "azurerm_storage_account" "main" {
  name                     = "voiceagentstore${var.env}"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"             # dev/staging: LRS is fine
  # account_replication_type = "ZRS"           # prod: zone-redundant
  min_tls_version          = "TLS1_2"
  blob_properties {
    delete_retention_policy {
      days = 7                                  # soft-delete safety net
    }
  }
}

resource "azurerm_storage_container" "recordings" {
  name                  = "recordings"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"             # never public
}

resource "azurerm_storage_container" "transcripts" {
  name                  = "transcripts"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "agent_events" {
  name                  = "agent-events"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}
```

### Azure Free Tier Note

Azure Blob Storage includes 5 GB of LRS capacity free for 12 months on the free account. During dev and early staging, call recordings at ~1 MB/call means 5,000 test calls before you exceed the free tier — more than enough to build and validate the entire system.

---

## 4. Database Connection Pool

```python
# shared/clients/db.py

import asyncpg
from contextlib import asynccontextmanager

class DatabasePool:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            self.dsn,
            min_size=5,
            max_size=20,
            command_timeout=5.0,       # hard 5s query timeout
            server_settings={
                "application_name": "voice-agent",
            }
        )

    @asynccontextmanager
    async def acquire(self):
        async with self.pool.acquire() as conn:
            yield conn

    async def close(self):
        await self.pool.close()
```

---

## 5. Key Queries (Optimized)

### Insert call on start

```python
async def create_call_record(conn, call_sid: str, tenant_id: str, caller_phone: str):
    await conn.execute("""
        INSERT INTO calls (call_sid, tenant_id, caller_phone, call_outcome)
        VALUES ($1, $2, $3, 'in_progress')
    """, call_sid, tenant_id, caller_phone)
```

### Update call on booking

```python
async def update_call_booked(conn, call_sid: str, job_data: dict):
    await conn.execute("""
        UPDATE calls SET
            call_outcome = 'booked',
            job_id = $2,
            tech_name = $3,
            booking_confirmed = true,
            updated_at = NOW()
        WHERE call_sid = $1
    """, call_sid, job_data["job_id"], job_data["tech_name"])
```

### Analytics: conversion rate by tenant

```sql
SELECT
    tenant_id,
    COUNT(*) FILTER (WHERE call_outcome = 'booked') AS booked,
    COUNT(*) AS total,
    ROUND(100.0 * COUNT(*) FILTER (WHERE call_outcome = 'booked') / COUNT(*), 1) AS conversion_pct,
    AVG(duration_seconds) AS avg_call_duration,
    AVG(estimate_max) AS avg_estimate
FROM calls
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY tenant_id
ORDER BY conversion_pct DESC;
```

---

## 6. Migration Strategy

```bash
# Create initial migration
alembic init alembic
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head

# Per-feature migration
alembic revision -m "add_pricing_catalog"
alembic upgrade head
```

All migrations are **non-destructive** — no DROP TABLE, no column removals. Only additive changes. Rollback = run down migration.

---

## Next: [07_Infra_DevOps.Plan.md](./07_Infra_DevOps.Plan.md)
