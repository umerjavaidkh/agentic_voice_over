# services/agent-brain/nodes/dispatcher_node.py

from shared.clients.dispatch_client import DispatchClient
from shared.models.agent_state import AgentState


async def _send_confirmation_sms(state: AgentState, *, confirmation_number: str, business_name: str) -> None:
    from sms import send_booking_confirmation

    await send_booking_confirmation(
        to_phone=state.caller_phone,
        tech_name=state.assigned_technician.name,
        eta_window=state.dispatch_eta or "soon",
        address=state.address or "",
        estimate_range=f"${state.estimate_min:.0f}–${state.estimate_max:.0f}",
        confirmation_number=confirmation_number,
        business_name=business_name,
    )


async def dispatcher_node(state: AgentState) -> AgentState:
    client = DispatchClient(tenant_id=state.tenant_id)

    try:
        job_result = await client.create_job({
            "caller_name": state.caller_name,
            "caller_phone": state.caller_phone,
            "address": state.address,
            "problem": state.problem_description,
            "service_category": state.service_category,
            "urgency": state.urgency_level,
            "estimate_min": state.estimate_min,
            "estimate_max": state.estimate_max,
            "tech_id": state.assigned_technician.tech_id,
            "business_name": "Dallas Plumbing Co.",
        })

        state.job_id = job_result["job_id"]
        state.booking_confirmed = job_result.get("booking_confirmed", True)
        await _send_confirmation_sms(
            state,
            confirmation_number=job_result.get("confirmation_number", state.job_id),
            business_name=job_result.get("business_name", "Home Services"),
        )
        state.agent_response = (
            f"You're all set, {state.caller_name}. "
            f"{state.assigned_technician.name} will be there "
            f"{state.dispatch_eta}. "
            f"I'm sending a text confirmation to {state.caller_phone} now. "
            f"Is there anything else I can help with?"
        )
    except Exception as e:
        state.fallback_triggered = True
        state.error_message = str(e)
        state.agent_response = (
            "I'm having trouble completing the booking on my end. "
            "Let me take your details and have our team call you right back."
        )

    return state
