import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import PlainTextResponse, Response

from barge_in import CallSession
from config import settings
from room_manager import RoomManager
from stt_client import DeepgramSTT
from tts_client import ElevenLabsTTS
from twilio_sip import handle_incoming

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.room_manager = RoomManager(
        settings.livekit_url,
        settings.livekit_api_key,
        settings.livekit_api_secret,
    )
    app.state.active_calls: dict[str, dict[str, Any]] = {}
    yield
    app.state.active_calls.clear()


app = FastAPI(title="voice-gateway", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "voice-gateway"}


@app.post("/call/incoming")
async def call_incoming(
    request: Request,
    CallSid: str = Form(...),
    tenant_id: str = Query(..., description="Tenant ID from webhook URL"),
):
    """New inbound call — spawn LiveKit room, wire voice pipeline, return TwiML."""
    if not settings.livekit_sip_domain:
        return PlainTextResponse(
            content="LIVEKIT_SIP_DOMAIN is not configured",
            status_code=503,
        )

    room_manager: RoomManager = request.app.state.room_manager
    room_name = await room_manager.create_call_room(CallSid, tenant_id)

    stt = DeepgramSTT(settings.deepgram_api_key)
    tts = ElevenLabsTTS(settings.elevenlabs_api_key)
    session = CallSession()

    request.app.state.active_calls[CallSid] = {
        "tenant_id": tenant_id,
        "room_name": room_name,
        "stt": stt,
        "tts": tts,
        "session": session,
    }

    logger.info(
        "call session wired",
        extra={"call_sid": CallSid, "tenant_id": tenant_id, "room_name": room_name},
    )

    twiml = handle_incoming(CallSid, tenant_id, settings.livekit_sip_domain)
    return PlainTextResponse(content=twiml, media_type="text/xml")


@app.post("/call/status")
async def call_status(
    request: Request,
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

    if CallStatus in ("completed", "failed", "busy", "no-answer", "canceled"):
        active_call = request.app.state.active_calls.pop(CallSid, None)
        if active_call:
            await request.app.state.room_manager.close_room(active_call["room_name"])

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
