from twilio.twiml.voice_response import Dial, VoiceResponse


def handle_incoming(call_sid: str, tenant_id: str, livekit_sip_domain: str) -> str:
    """Build TwiML that routes the inbound call to LiveKit via SIP."""
    response = VoiceResponse()
    dial = Dial()
    sip_uri = f"sip:{tenant_id}_{call_sid}@{livekit_sip_domain}"
    dial.sip(sip_uri)
    response.append(dial)
    return str(response)
