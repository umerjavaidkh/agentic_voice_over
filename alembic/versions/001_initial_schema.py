"""initial_schema — tenants, calls, conversation_turns, technicians

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-06-10

Enables pgvector and creates core tables from docs/06_Data_Layer.Plan.md section 1.
pricing_catalog is in 002_pricing_catalog (docs/04_Pricing_Engine.Plan.md section 2.1).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE tenants (
            id                  TEXT PRIMARY KEY,
            business_name       TEXT NOT NULL,
            phone_number        TEXT NOT NULL,
            timezone            TEXT DEFAULT 'UTC',
            fsm_type            TEXT NOT NULL,
            service_categories  TEXT[] DEFAULT '{}',
            is_active           BOOLEAN DEFAULT true,
            created_at          TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE calls (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            call_sid            TEXT UNIQUE NOT NULL,
            tenant_id           TEXT NOT NULL REFERENCES tenants(id),
            caller_phone        TEXT NOT NULL,
            caller_name         TEXT,
            address             TEXT,

            problem_description TEXT,
            service_category    TEXT,
            appliance_type      TEXT,
            urgency_level       TEXT,

            estimate_min        DECIMAL(10,2),
            estimate_max        DECIMAL(10,2),
            pricing_confidence  DECIMAL(4,3),

            call_outcome        TEXT DEFAULT 'in_progress',
            job_id              TEXT,
            tech_name           TEXT,
            booking_confirmed   BOOLEAN DEFAULT false,
            fallback_triggered  BOOLEAN DEFAULT false,
            human_handoff       BOOLEAN DEFAULT false,

            duration_seconds    INT,
            turn_count          INT DEFAULT 0,
            recording_blob_path TEXT,

            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX calls_tenant_idx ON calls (tenant_id, created_at DESC)
    """)

    op.execute("""
        CREATE INDEX calls_outcome_idx ON calls (tenant_id, call_outcome)
    """)

    op.execute("""
        CREATE TABLE conversation_turns (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            call_id         UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
            turn_number     INT NOT NULL,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            node_name       TEXT,
            latency_ms      INT,
            token_count     INT,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX turns_call_idx ON conversation_turns (call_id, turn_number)
    """)

    op.execute("""
        CREATE TABLE technicians (
            id                      TEXT NOT NULL,
            tenant_id               TEXT NOT NULL REFERENCES tenants(id),
            name                    TEXT NOT NULL,
            phone                   TEXT,
            email                   TEXT,
            specialties             TEXT[] DEFAULT '{}',
            is_active               BOOLEAN DEFAULT true,
            current_lat             DECIMAL(10,8),
            current_lng             DECIMAL(11,8),
            last_location_update    TIMESTAMPTZ,
            synced_at               TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (id, tenant_id)
        )
    """)

    op.execute("""
        CREATE INDEX technicians_tenant_idx ON technicians (tenant_id, is_active)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS technicians_tenant_idx")
    op.execute("DROP TABLE IF EXISTS technicians")

    op.execute("DROP INDEX IF EXISTS turns_call_idx")
    op.execute("DROP TABLE IF EXISTS conversation_turns")

    op.execute("DROP INDEX IF EXISTS calls_outcome_idx")
    op.execute("DROP INDEX IF EXISTS calls_tenant_idx")
    op.execute("DROP TABLE IF EXISTS calls")

    op.execute("DROP TABLE IF EXISTS tenants")

    op.execute("DROP EXTENSION IF EXISTS vector")
