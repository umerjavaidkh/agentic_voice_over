from unittest.mock import AsyncMock, MagicMock

import pytest

from embedder import PricingEmbedder


SAMPLE_ENTRY = {
    "service_name": "Water heater thermocouple replacement",
    "service_category": "plumbing",
    "description": "Replace faulty thermocouple on gas water heater, pilot light won't stay lit",
    "min_price": 120,
    "max_price": 250,
    "typical_duration_hours": 1.0,
}


def _mock_openai_client(embedding: list[float] | None = None):
    mock_embedding = MagicMock()
    mock_embedding.embedding = embedding or [0.1] * 1536
    mock_response = MagicMock()
    mock_response.data = [mock_embedding]
    mock_oai = MagicMock()
    mock_oai.embeddings.create = AsyncMock(return_value=mock_response)
    return mock_oai


def _mock_db_pool():
    mock_conn = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_conn
    mock_cm.__aexit__.return_value = None
    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_cm
    return mock_pool, mock_conn


def test_build_embed_text_excludes_price_fields():
    embedder = PricingEmbedder(db_pool=MagicMock(), openai_client=MagicMock())

    text = embedder.build_embed_text(SAMPLE_ENTRY)

    assert "Water heater thermocouple replacement" in text
    assert "Category: plumbing" in text
    assert "pilot light won't stay lit" in text
    assert "120" not in text
    assert "250" not in text
    assert "min_price" not in text
    assert "max_price" not in text


@pytest.mark.asyncio
async def test_embed_catalog_entry_calls_openai_with_model_and_text():
    mock_oai = _mock_openai_client()
    embedder = PricingEmbedder(db_pool=MagicMock(), openai_client=mock_oai)

    result = await embedder.embed_catalog_entry(SAMPLE_ENTRY)

    mock_oai.embeddings.create.assert_awaited_once_with(
        input=embedder.build_embed_text(SAMPLE_ENTRY),
        model=PricingEmbedder.MODEL,
    )
    assert len(result) == 1536


@pytest.mark.asyncio
async def test_seed_tenant_catalog_inserts_correct_number_of_rows():
    entries = [
        SAMPLE_ENTRY,
        {
            "service_name": "Drain cleaning",
            "service_category": "plumbing",
            "description": "Clear blocked or slow drain",
            "min_price": 100,
            "max_price": 350,
            "typical_duration_hours": 1.5,
        },
        {
            "service_name": "Furnace repair",
            "service_category": "hvac",
            "description": "Diagnose and repair furnace not heating",
            "min_price": 200,
            "max_price": 700,
        },
    ]
    mock_pool, mock_conn = _mock_db_pool()
    mock_oai = _mock_openai_client()
    embedder = PricingEmbedder(db_pool=mock_pool, openai_client=mock_oai)

    await embedder.seed_tenant_catalog("t_abc123", entries)

    assert mock_oai.embeddings.create.await_count == len(entries)
    assert mock_conn.execute.await_count == len(entries)

    first_call = mock_conn.execute.await_args_list[0]
    assert first_call.args[1] == "t_abc123"
    assert first_call.args[2] == entries[0]["service_name"]
    assert first_call.args[5] == entries[0]["min_price"]
    assert first_call.args[6] == entries[0]["max_price"]
    assert first_call.args[7] == entries[0]["typical_duration_hours"]

    third_call = mock_conn.execute.await_args_list[2]
    assert third_call.args[7] == 2.0  # default typical_duration_hours
