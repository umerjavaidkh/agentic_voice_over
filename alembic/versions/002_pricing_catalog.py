"""pricing_catalog — vector-indexed price catalog per tenant

Revision ID: 002_pricing_catalog
Revises: 001_initial_schema
Create Date: 2026-06-10

Source: migrations/002_pricing_catalog.sql (docs/04_Pricing_Engine.Plan.md section 2.1)
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "002_pricing_catalog"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SQL_PATH = Path(__file__).resolve().parents[2] / "migrations" / "002_pricing_catalog.sql"


def _run_sql_file() -> None:
    raw = _SQL_PATH.read_text()
    statements = [
        s.strip()
        for s in raw.split(";")
        if s.strip() and not all(line.strip().startswith("--") or not line.strip() for line in s.splitlines())
    ]
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    _run_sql_file()


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS pricing_catalog_tenant_idx")
    op.execute("DROP INDEX IF EXISTS pricing_catalog_embedding_idx")
    op.execute("DROP TABLE IF EXISTS pricing_catalog")
