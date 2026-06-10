import pytest

from shared.models.agent_state import AgentState, ServiceCategory, Technician


def _make_state(*, message: str, is_emergency: bool = False) -> AgentState:
    return AgentState(
        call_sid="CA123",
        tenant_id="t_abc",
        caller_phone="+15551234567",
        caller_name="Ahmed",
        address="123 Main Street, Dubai",
        problem_description="Water heater leaking",
        service_category=ServiceCategory.PLUMBING,
        estimate_min=200.0,
        estimate_max=450.0,
        is_emergency=is_emergency,
        assigned_technician=Technician(
            tech_id="tech_1",
            name="Mike",
            phone="+15559876543",
            distance_km=4.2,
            eta_minutes=45,
            specialty=ServiceCategory.PLUMBING,
        ),
        conversation_history=[{"role": "user", "content": message}],
    )


@pytest.mark.asyncio
async def test_qualifier_node_emergency_response():
    state = _make_state(message="yes", is_emergency=True)

    from nodes.qualifier_node import qualifier_node

    result = await qualifier_node(state)

    assert "That sounds urgent" in result.agent_response
    assert "Mike" in result.agent_response
    assert "123 Main Street, Dubai" in result.agent_response
    assert "within 45 minutes" in result.agent_response
    assert "$200–$450" in result.agent_response
    assert "Shall I confirm that booking?" in result.agent_response


@pytest.mark.asyncio
async def test_qualifier_node_scheduled_response():
    state = _make_state(message="maybe", is_emergency=False)

    from nodes.qualifier_node import qualifier_node

    result = await qualifier_node(state)

    assert "I can schedule a technician" in result.agent_response
    assert "tomorrow between 9 AM and 12 PM" in result.agent_response
    assert "$200–$450" in result.agent_response
    assert "Does that work for you?" in result.agent_response


@pytest.mark.parametrize(
    "phrase",
    [
        "yes",
        "yeah that works for me",
        "sure",
        "go ahead",
        "book it please",
        "ok",
        "confirm",
        "yes please book it",
        "yeah go ahead and confirm",
        "sure ok book it",
    ],
)
def test_should_dispatch_confirm_phrases(phrase):
    from nodes.qualifier_node import should_dispatch

    state = _make_state(message=phrase)
    assert should_dispatch(state) == "dispatch"


@pytest.mark.parametrize(
    "phrase",
    [
        "no",
        "cancel that",
        "wait a minute",
        "hold on",
        "not yet",
    ],
)
def test_should_dispatch_deny_phrases(phrase):
    from nodes.qualifier_node import should_dispatch

    state = _make_state(message=phrase)
    assert should_dispatch(state) == "clarify"


@pytest.mark.parametrize(
    "phrase",
    [
        "what time tomorrow?",
        "how much is the service call fee?",
        "can you repeat the estimate?",
    ],
)
def test_should_dispatch_re_ask_phrases(phrase):
    from nodes.qualifier_node import should_dispatch

    state = _make_state(message=phrase)
    assert should_dispatch(state) == "re_ask"
