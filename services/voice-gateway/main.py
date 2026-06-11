import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Form, Query, Request, WebSocket
from fastapi.responses import PlainTextResponse, Response

from call_finisher import download_twilio_recording, finalize_call
from call_pipeline import CallPipeline
from config import settings
from room_manager import RoomManager
from shared.clients.call_records import create_call_record
from shared.clients.db import DatabasePool
from shared.clients.redis_client import RedisClient
from twilio_media_pipeline import TwilioMediaPipeline
from twilio_sip import handle_incoming
from twilio_stream import handle_incoming_stream, public_base_to_ws_url

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.room_manager = RoomManager(
        settings.livekit_url,
        settings.livekit_api_key,
        settings.livekit_api_secret,
        sip_trunk_id=settings.livekit_sip_trunk_id,
    )
    app.state.redis = RedisClient(settings.redis_url)
    app.state.db = DatabasePool(settings.postgres_dsn)
    try:
        await app.state.db.connect()
    except Exception:
        logger.exception("database connection failed; call records disabled")
        app.state.db = None

    app.state.active_calls: dict[str, dict[str, Any]] = {}
    yield

    app.state.active_calls.clear()
    await app.state.redis.close()
    if app.state.db:
        await app.state.db.close()


app = FastAPI(title="voice-gateway", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "voice-gateway"}


@app.post("/call/incoming")
async def call_incoming(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(default=""),
    tenant_id: str = Query(..., description="Tenant ID from webhook URL"),
):
    """New inbound call — return TwiML and wire the voice pipeline."""
    if settings.voice_transport == "twilio_stream":
        if not settings.public_base_url:
            return PlainTextResponse(
                content="PUBLIC_BASE_URL is not configured (set your ngrok HTTPS URL)",
                status_code=503,
            )

        await request.app.state.redis.set_call_meta(
            CallSid,
            {
                "tenant_id": tenant_id,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "caller_phone": From,
            },
        )

        if request.app.state.db:
            try:
                async with request.app.state.db.acquire() as conn:
                    await create_call_record(conn, CallSid, tenant_id, From)
            except Exception:
                logger.exception(
                    "failed to create call record",
                    extra={"call_sid": CallSid, "tenant_id": tenant_id},
                )

        ws_url = public_base_to_ws_url(settings.public_base_url, "/ws/media")
        twiml = handle_incoming_stream(ws_url, tenant_id, caller_phone=From)
        logger.info(
            "call session wired (twilio stream)",
            extra={"call_sid": CallSid, "tenant_id": tenant_id, "ws_url": ws_url},
        )
        return PlainTextResponse(content=twiml, media_type="text/xml")

    if not settings.livekit_sip_domain:
        return PlainTextResponse(
            content="LIVEKIT_SIP_DOMAIN is not configured",
            status_code=503,
        )

    room_manager: RoomManager = request.app.state.room_manager
    room_name, dispatch_rule_id = await room_manager.create_call_room(CallSid, tenant_id)

    pipeline = CallPipeline(
        call_sid=CallSid,
        tenant_id=tenant_id,
        caller_phone=From,
        room_name=room_name,
        livekit_url=settings.livekit_url,
        livekit_api_key=settings.livekit_api_key,
        livekit_api_secret=settings.livekit_api_secret,
        agent_brain_url=settings.agent_brain_url,
        business_name=settings.business_name,
        deepgram_api_key=settings.deepgram_api_key,
        elevenlabs_api_key=settings.elevenlabs_api_key,
        elevenlabs_voice_id=settings.elevenlabs_voice_id,
        elevenlabs_model_id=settings.elevenlabs_model_id,
        tts_provider=settings.tts_provider,
        deepgram_tts_model=settings.deepgram_tts_model,
    )
    pipeline_task = asyncio.create_task(pipeline.run())
    try:
        await pipeline.wait_ready(timeout=15.0)
    except asyncio.TimeoutError:
        logger.warning(
            "voice bot not ready before TwiML; caller may hear silence initially",
            extra={"call_sid": CallSid, "tenant_id": tenant_id},
        )

    request.app.state.active_calls[CallSid] = {
        "tenant_id": tenant_id,
        "room_name": room_name,
        "dispatch_rule_id": dispatch_rule_id,
        "pipeline": pipeline,
        "pipeline_task": pipeline_task,
    }

    await request.app.state.redis.set_call_meta(
        CallSid,
        {
            "tenant_id": tenant_id,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "room_name": room_name,
        },
    )

    if request.app.state.db:
        try:
            async with request.app.state.db.acquire() as conn:
                await create_call_record(conn, CallSid, tenant_id, From)
        except Exception:
            logger.exception(
                "failed to create call record",
                extra={"call_sid": CallSid, "tenant_id": tenant_id},
            )

    logger.info(
        "call session wired (livekit sip)",
        extra={"call_sid": CallSid, "tenant_id": tenant_id, "room_name": room_name},
    )

    twiml = handle_incoming(
        CallSid,
        tenant_id,
        settings.livekit_sip_domain,
        sip_username=settings.livekit_sip_username,
        sip_password=settings.livekit_sip_password,
    )
    return PlainTextResponse(content=twiml, media_type="text/xml")


@app.websocket("/ws/media")
async def twilio_media_ws(websocket: WebSocket):
    """Twilio Media Streams WebSocket — caller audio in/out without LiveKit SIP."""
    await websocket.accept()
    pipeline = TwilioMediaPipeline(
        websocket,
        deepgram_api_key=settings.deepgram_api_key,
        agent_brain_url=settings.agent_brain_url,
        business_name=settings.business_name,
        tts_provider=settings.tts_provider,
        deepgram_tts_model=settings.deepgram_tts_model,
        elevenlabs_api_key=settings.elevenlabs_api_key,
        elevenlabs_voice_id=settings.elevenlabs_voice_id,
        elevenlabs_model_id=settings.elevenlabs_model_id,
    )
    await pipeline.run()


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
            pipeline = active_call.get("pipeline")
            if pipeline:
                pipeline.stop()
            pipeline_task = active_call.get("pipeline_task")
            if pipeline_task and not pipeline_task.done():
                try:
                    await asyncio.wait_for(pipeline_task, timeout=10.0)
                except asyncio.TimeoutError:
                    pipeline_task.cancel()
            room_name = active_call.get("room_name")
            if room_name:
                await request.app.state.room_manager.close_room(
                    room_name,
                    active_call.get("dispatch_rule_id", ""),
                )

    return Response(status_code=204)


@app.post("/call/recording")
async def call_recording(
    request: Request,
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

    if not request.app.state.db:
        logger.warning("recording skipped: database not available", extra={"call_sid": CallSid})
        return Response(status_code=204)

    resolved_tenant_id = tenant_id
    if not resolved_tenant_id:
        active_call = request.app.state.active_calls.get(CallSid)
        if active_call:
            resolved_tenant_id = active_call["tenant_id"]
        else:
            meta = await request.app.state.redis.get_call_meta(CallSid)
            if meta:
                resolved_tenant_id = meta.get("tenant_id")

    if not resolved_tenant_id:
        logger.warning("recording skipped: tenant_id unknown", extra={"call_sid": CallSid})
        return Response(status_code=204)

    try:
        recording_bytes = await download_twilio_recording(
            RecordingUrl,
            settings.twilio_account_sid,
            settings.twilio_auth_token,
        )
        await finalize_call(
            CallSid,
            resolved_tenant_id,
            recording_bytes,
            request.app.state.db,
        )
    except Exception:
        logger.exception(
            "failed to finalize call recording",
            extra={"call_sid": CallSid, "tenant_id": resolved_tenant_id},
        )

    return Response(status_code=204)
