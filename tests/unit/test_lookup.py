from unittest.mock import AsyncMock, MagicMock

import pytest

from lookup import get_category_fallback, lookup_price


def _mock_openai_client():
    mock_embedding = MagicMock()
    mock_embedding.embedding = [0.2] * 1536
    mock_response = MagicMock()
    mock_response.data = [mock_embedding]
    mock_oai = MagicMock()
    mock_oai.embeddings.create = AsyncMock(return_value=mock_response)
    return mock_oai


def _mock_db_pool(rows):
    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(return_value=rows)
    return mock_pool


HIGH_CONFIDENCE_ROWS = [
    {
        "service_name": "Water heater thermocouple replacement",
        "service_category": "plumbing",
        "min_price": 120,
        "max_price": 250,
        "typical_duration_hours": 1.0,
        "emergency_surcharge_pct": 25.0,
        "similarity": 0.88,
    },
    {
        "service_name": "Water heater replacement",
        "service_category": "plumbing",
        "min_price": 800,
        "max_price": 1800,
        "typical_duration_hours": 3.0,
        "emergency_surcharge_pct": 25.0,
        "similarity": 0.76,
    },
]


@pytest.mark.asyncio
async def test_high_confidence_match_uses_similarity_weighted_average():
    mock_oai = _mock_openai_client()
    mock_pool = _mock_db_pool(HIGH_CONFIDENCE_ROWS)

    result = await lookup_price(
        description="pilot light won't stay lit on gas water heater",
        category="plumbing",
        tenant_id="t_abc123",
        is_emergency=True,
        db_pool=mock_pool,
        oai_client=mock_oai,
    )

    total_weight = 0.88 + 0.76
    weighted_min = (120 * 0.88 + 800 * 0.76) / total_weight
    weighted_max = (250 * 0.88 + 1800 * 0.76) / total_weight
    surcharge = 0.25

    mock_oai.embeddings.create.assert_awaited_once()
    mock_pool.fetch.assert_awaited_once()
    assert result.service_name == "Water heater thermocouple replacement"
    assert result.service_category == "plumbing"
    assert result.min_price == round(weighted_min, -1)
    assert result.max_price == round(weighted_max, -1)
    assert result.emergency_min == round(weighted_min * (1 + surcharge), -1)
    assert result.emergency_max == round(weighted_max * (1 + surcharge), -1)
    assert result.confidence == pytest.approx(total_weight / 2)
    assert result.typical_duration_hours == 1.0


@pytest.mark.asyncio
async def test_low_confidence_returns_category_fallback():
    mock_oai = _mock_openai_client()
    mock_pool = _mock_db_pool([])

    result = await lookup_price(
        description="vague plumbing issue",
        category="plumbing",
        tenant_id="t_abc123",
        is_emergency=True,
        db_pool=mock_pool,
        oai_client=mock_oai,
    )

    expected = get_category_fallback("plumbing", is_emergency=True)

    assert result == expected
    assert result.confidence == 0.0
    assert result.min_price == 150
    assert result.max_price == 600
    assert result.emergency_min == 190
    assert result.emergency_max == 750


@pytest.mark.asyncio
async def test_empty_results_returns_general_fallback():
    mock_oai = _mock_openai_client()
    mock_pool = _mock_db_pool([])

    result = await lookup_price(
        description="something completely unrelated",
        category=None,
        tenant_id="t_abc123",
        is_emergency=False,
        db_pool=mock_pool,
        oai_client=mock_oai,
    )

    expected = get_category_fallback(None, is_emergency=False)

    assert result == expected
    assert result.service_category == "general"
    assert result.confidence == 0.0
    assert result.min_price == 100
    assert result.max_price == 500
    assert result.emergency_min == 100
    assert result.emergency_max == 500
