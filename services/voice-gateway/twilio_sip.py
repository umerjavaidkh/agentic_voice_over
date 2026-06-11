from twilio.twiml.voice_response import Dial, VoiceResponse


def handle_incoming(
    call_sid: str,
    tenant_id: str,
    livekit_sip_domain: str,
    *,
    sip_username: str = "",
    sip_password: str = "",
) -> str:
    """Build TwiML that routes the inbound call to LiveKit via SIP over TLS."""
    response = VoiceResponse()
    dial = Dial()
    # LiveKit requires TLS; Twilio defaults to UDP without ;transport=tls
    sip_uri = f"sip:{tenant_id}_{call_sid}@{livekit_sip_domain};transport=tls"
    if sip_username and sip_password:
        dial.sip(sip_uri, username=sip_username, password=sip_password)
    else:
        dial.sip(sip_uri)
    response.append(dial)
    return str(response)
