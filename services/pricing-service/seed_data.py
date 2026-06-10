# pricing-service/seed_data.py

import argparse
import asyncio
import os
import sys
from collections import Counter

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
    {
        "service_name": "Toilet repair and replacement",
        "service_category": "plumbing",
        "description": "Repair running toilet, replace wax ring, fix flush valve, or install new toilet bowl and tank",
        "min_price": 150,
        "max_price": 450,
        "typical_duration_hours": 1.5,
    },
    {
        "service_name": "Garbage disposal installation",
        "service_category": "plumbing",
        "description": "Install or replace kitchen garbage disposal unit, wiring, drain connection, and leak testing",
        "min_price": 200,
        "max_price": 500,
        "typical_duration_hours": 2.0,
    },
    {
        "service_name": "Sewer line backup clearing",
        "service_category": "plumbing",
        "description": "Clear main sewer line backup, multiple drains backing up, hydro jetting or snake auger service",
        "min_price": 250,
        "max_price": 900,
        "typical_duration_hours": 3.0,
    },
    {
        "service_name": "Water softener installation",
        "service_category": "plumbing",
        "description": "Install whole-home water softener system, bypass valve, drain line, and initial calibration",
        "min_price": 600,
        "max_price": 1400,
        "typical_duration_hours": 4.0,
    },
    {
        "service_name": "Faucet replacement",
        "service_category": "plumbing",
        "description": "Replace kitchen or bathroom faucet, shut off supply lines, install new fixture, test for leaks",
        "min_price": 120,
        "max_price": 300,
        "typical_duration_hours": 1.0,
    },
    {
        "service_name": "Sump pump repair",
        "service_category": "plumbing",
        "description": "Diagnose and repair basement sump pump not running, float switch replacement, backup pump install",
        "min_price": 180,
        "max_price": 550,
        "typical_duration_hours": 2.0,
    },
    {
        "service_name": "Gas line leak repair",
        "service_category": "plumbing",
        "description": "Emergency gas line leak detection and repair, appliance shutoff, pressure test, code compliance",
        "min_price": 350,
        "max_price": 1200,
        "typical_duration_hours": 3.0,
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
    {
        "service_name": "AC unit installation",
        "service_category": "hvac",
        "description": "Install new central air conditioning unit, refrigerant lines, electrical hookup, and commissioning",
        "min_price": 3500,
        "max_price": 7500,
        "typical_duration_hours": 8.0,
    },
    {
        "service_name": "Duct cleaning",
        "service_category": "hvac",
        "description": "Professional HVAC duct cleaning, remove dust and allergens, sanitize supply and return vents",
        "min_price": 300,
        "max_price": 700,
        "typical_duration_hours": 3.0,
    },
    {
        "service_name": "Smart thermostat installation",
        "service_category": "hvac",
        "description": "Install and configure smart thermostat, C-wire adapter if needed, Wi-Fi setup, system compatibility check",
        "min_price": 150,
        "max_price": 400,
        "typical_duration_hours": 1.5,
    },
    {
        "service_name": "Heat pump repair",
        "service_category": "hvac",
        "description": "Repair heat pump not heating or cooling, defrost cycle issues, reversing valve, refrigerant leak",
        "min_price": 250,
        "max_price": 900,
        "typical_duration_hours": 3.0,
    },
    {
        "service_name": "Mini-split installation",
        "service_category": "hvac",
        "description": "Install ductless mini-split system, wall mount unit, outdoor condenser, line set, and electrical",
        "min_price": 2500,
        "max_price": 5500,
        "typical_duration_hours": 6.0,
    },
    {
        "service_name": "HVAC seasonal maintenance",
        "service_category": "hvac",
        "description": "Seasonal tune-up, filter replacement, coil cleaning, electrical inspection, efficiency check",
        "min_price": 120,
        "max_price": 250,
        "typical_duration_hours": 1.5,
    },
    {
        "service_name": "Refrigerant recharge",
        "service_category": "hvac",
        "description": "Recharge AC refrigerant, leak check, pressure test, restore cooling performance",
        "min_price": 200,
        "max_price": 650,
        "typical_duration_hours": 2.0,
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
    {
        "service_name": "Shingle roof replacement",
        "service_category": "roofing",
        "description": "Full asphalt shingle roof replacement, tear-off old shingles, underlayment, ridge vent, cleanup",
        "min_price": 8000,
        "max_price": 18000,
        "typical_duration_hours": 16.0,
    },
    {
        "service_name": "Gutter cleaning and repair",
        "service_category": "roofing",
        "description": "Clean clogged gutters and downspouts, reseal joints, replace damaged sections, ensure proper drainage",
        "min_price": 150,
        "max_price": 450,
        "typical_duration_hours": 2.0,
    },
    {
        "service_name": "Skylight leak repair",
        "service_category": "roofing",
        "description": "Repair leaking skylight, reflash curb, replace sealant, fix water intrusion around frame",
        "min_price": 350,
        "max_price": 900,
        "typical_duration_hours": 3.0,
    },
    {
        "service_name": "Flat roof repair",
        "service_category": "roofing",
        "description": "Repair flat or low-slope roof membrane, patch blisters, reseal seams, ponding water remediation",
        "min_price": 500,
        "max_price": 2000,
        "typical_duration_hours": 5.0,
    },
    {
        "service_name": "Roof inspection",
        "service_category": "roofing",
        "description": "Comprehensive roof inspection, document shingle condition, flashing, ventilation, and repair recommendations",
        "min_price": 200,
        "max_price": 400,
        "typical_duration_hours": 2.0,
    },
    {
        "service_name": "Chimney flashing repair",
        "service_category": "roofing",
        "description": "Repair chimney flashing leak, step flashing, counter flashing, mortar cap inspection",
        "min_price": 300,
        "max_price": 800,
        "typical_duration_hours": 3.0,
    },
]


def dry_run(tenant_id: str) -> None:
    categories = Counter(entry["service_category"] for entry in CATALOG_SEED)
    print(f"tenant_id: {tenant_id}")
    print(f"entries: {len(CATALOG_SEED)}")
    for category, count in sorted(categories.items()):
        print(f"  {category}: {count}")
    for entry in CATALOG_SEED:
        print(f"  - {entry['service_name']} ({entry['service_category']})")


async def seed_catalog(tenant_id: str) -> int:
    from openai import AsyncOpenAI

    import asyncpg

    from embedder import PricingEmbedder

    database_url = os.environ["DATABASE_URL"]
    openai_api_key = os.environ["OPENAI_API_KEY"]

    pool = await asyncpg.create_pool(database_url)
    try:
        embedder = PricingEmbedder(pool, AsyncOpenAI(api_key=openai_api_key))
        await embedder.seed_tenant_catalog(tenant_id, CATALOG_SEED)
    finally:
        await pool.close()

    return len(CATALOG_SEED)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed pricing catalog for a tenant")
    parser.add_argument("--tenant-id", required=True, help="Tenant ID to seed")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print seed plan without embedding or inserting",
    )
    args = parser.parse_args()

    if args.dry_run:
        dry_run(args.tenant_id)
        return 0

    try:
        inserted = asyncio.run(seed_catalog(args.tenant_id))
    except KeyError as exc:
        print(f"Missing required environment variable: {exc.args[0]}", file=sys.stderr)
        return 1

    print(f"Seeded {inserted} catalog entries for tenant {args.tenant_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
