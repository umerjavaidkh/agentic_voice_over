import pytest

from prompts import get_response_prompt, get_system_prompt


def test_get_system_prompt_intent():
    prompt = get_system_prompt("intent")
    assert "urgency_signal" in prompt
    assert "service_category" in prompt


def test_get_system_prompt_unknown_node():
    with pytest.raises(KeyError, match="Unknown system prompt"):
        get_system_prompt("unknown")


def test_get_response_prompt_intent():
    assert "address" in get_response_prompt("intent").lower()


def test_get_response_prompt_entity_requires_field():
    assert get_response_prompt("entity", field="address").startswith("What's the address")
