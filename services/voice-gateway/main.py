import logging

from fastapi import FastAPI, Form, Query
from fastapi.responses import PlainTextResponse, Response

from config import settings
from twilio_sip import handle_incoming

logger = logging.getLogger(__name__)

app = FastAPI(title="voice-gateway")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "voice-gateway"}


@app.post("/call/incoming")
async def call_incoming(
    CallSid: str = Form(...),
    tenant_id: str = Query(..., description="Tenant ID from webhook URL"),
):
    """New inbound call — return TwiML to dial LiveKit SIP URI."""
    if not settings.livekit_sip_domain:
        return PlainTextResponse(
            content="LIVEKIT_SIP_DOMAIN is not configured",
            status_code=503,
        )

    twiml = handle_incoming(CallSid, tenant_id, settings.livekit_sip_domain)
    return PlainTextResponse(content=twiml, media_type="text/xml")


@app.post("/call/status")
async def call_status(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    tenant_id: str | None = Query(default=None),
):
    """Twilio status callback (completed, failed, etc.)."""
    logger.info(
        "call status update",
        extra={
            "call_sid": CallSid,
            "call_status": CallStatus,
            "tenant_id": tenant_id,
        },
    )
    return Response(status_code=204)


@app.post("/call/recording")
async def call_recording(
    CallSid: str = Form(...),
    RecordingUrl: str = Form(...),
    RecordingSid: str = Form(default=""),
    tenant_id: str | None = Query(default=None),
):
    """Recording-ready webhook (dual-channel caller + agent tracks)."""
    logger.info(
        "recording ready",
        extra={
            "call_sid": CallSid,
            "recording_sid": RecordingSid,
            "recording_url": RecordingUrl,
            "tenant_id": tenant_id,
        },
    )
    return Response(status_code=204)
