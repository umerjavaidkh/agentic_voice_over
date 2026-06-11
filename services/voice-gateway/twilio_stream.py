# services/voice-gateway/twilio_stream.py

from twilio.twiml.voice_response import Connect, VoiceResponse


def handle_incoming_stream(
    ws_url: str,
    tenant_id: str,
    caller_phone: str = "",
) -> str:
    """Return TwiML that streams caller audio to our WebSocket (no LiveKit SIP)."""
    response = VoiceResponse()
    connect = Connect()
    stream = connect.stream(url=ws_url)
    stream.parameter(name="tenant_id", value=tenant_id)
    if caller_phone:
        stream.parameter(name="caller_phone", value=caller_phone)
    response.append(connect)
    return str(response)


def public_base_to_ws_url(public_base_url: str, path: str) -> str:
    base = public_base_url.rstrip("/")
    if base.startswith("https://"):
        ws_base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        ws_base = "ws://" + base[len("http://") :]
    else:
        ws_base = "wss://" + base
    return ws_base + path
