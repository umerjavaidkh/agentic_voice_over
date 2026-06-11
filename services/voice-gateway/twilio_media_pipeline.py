# services/voice-gateway/twilio_media_pipeline.py

import asyncio
import base64
import json
import logging
from dataclasses import dataclass

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from agent_brain_client import AgentBrainClient
from audio_convert import TWILIO_MULAW_FRAME, pcm16_16k_to_mulaw_8k
from scripts import GREETING_TEMPLATE, format_script
from stt_client import DeepgramSTT
from tts_client import create_tts

logger = logging.getLogger(__name__)


@dataclass
class _AudioChunk:
    data: bytes


class TwilioMediaPipeline:
    """Handle one Twilio Media Stream WebSocket session."""

    def __init__(
        self,
        websocket: WebSocket,
        *,
        deepgram_api_key: str,
        agent_brain_url: str,
        business_name: str,
        tts_provider: str,
        deepgram_tts_model: str,
        elevenlabs_api_key: str,
        elevenlabs_voice_id: str,
        elevenlabs_model_id: str,
    ):
        self._ws = websocket
        self._deepgram_api_key = deepgram_api_key
        self._agent_brain_url = agent_brain_url
        self._business_name = business_name
        self._tts = create_tts(
            provider=tts_provider,
            deepgram_api_key=deepgram_api_key,
            deepgram_tts_model=deepgram_tts_model,
            elevenlabs_api_key=elevenlabs_api_key,
            elevenlabs_voice_id=elevenlabs_voice_id,
            elevenlabs_model_id=elevenlabs_model_id,
        )
        self._stream_sid = ""
        self._call_sid = ""
        self._tenant_id = ""
        self._caller_phone = ""
        self._speaking = False
        self._stop = asyncio.Event()

    async def run(self) -> None:
        agent: AgentBrainClient | None = None
        stt_task: asyncio.Task | None = None
        audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        try:
            while not self._stop.is_set():
                raw = await self._ws.receive_text()
                message = json.loads(raw)
                event = message.get("event")

                if event == "connected":
                    continue

                if event == "start":
                    start = message.get("start", {})
                    self._stream_sid = start.get("streamSid", "")
                    self._call_sid = start.get("callSid", "")
                    custom = start.get("customParameters", {})
                    self._tenant_id = custom.get("tenant_id", "t_test")
                    self._caller_phone = custom.get("caller_phone", "")
                    logger.info(
                        "twilio media stream started",
                        extra={
                            "call_sid": self._call_sid,
                            "tenant_id": self._tenant_id,
                            "stream_sid": self._stream_sid,
                        },
                    )
                    agent = AgentBrainClient(
                        self._agent_brain_url,
                        self._call_sid,
                        self._tenant_id,
                        self._caller_phone,
                    )
                    await agent.connect()
                    stt_task = asyncio.create_task(
                        self._run_stt(audio_queue, agent)
                    )
                    greeting = format_script(
                        GREETING_TEMPLATE,
                        business_name=self._business_name,
                    )
                    await self._speak(greeting)
                    continue

                if event == "media":
                    if self._speaking:
                        continue
                    payload = message.get("media", {}).get("payload", "")
                    if payload:
                        await audio_queue.put(base64.b64decode(payload))
                    continue

                if event == "stop":
                    self._stop.set()
                    break

        except WebSocketDisconnect:
            logger.info(
                "twilio media stream disconnected",
                extra={"call_sid": self._call_sid},
            )
        except Exception:
            logger.exception(
                "twilio media pipeline failed",
                extra={"call_sid": self._call_sid, "tenant_id": self._tenant_id},
            )
        finally:
            self._stop.set()
            await audio_queue.put(None)
            if stt_task:
                stt_task.cancel()
                try:
                    await stt_task
                except asyncio.CancelledError:
                    pass
            if agent:
                await agent.close()

    async def _run_stt(
        self,
        audio_queue: asyncio.Queue[bytes | None],
        agent: AgentBrainClient,
    ) -> None:
        stt = DeepgramSTT(self._deepgram_api_key)

        async def audio_source():
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
                yield _AudioChunk(data=chunk)

        async def on_transcript(text: str, is_final: bool) -> None:
            if not is_final or not text.strip():
                return
            logger.info(
                "caller transcript",
                extra={"call_sid": self._call_sid, "text": text},
            )
            response = await agent.send_transcript(text)
            if response:
                await self._speak(response)

        await stt.stream_mulaw(audio_source(), on_transcript)

    async def _speak(self, text: str) -> None:
        if not self._stream_sid:
            return
        self._speaking = True
        try:
            pcm = await self._tts.synthesize_pcm16(text)
            mulaw = pcm16_16k_to_mulaw_8k(pcm)
            for offset in range(0, len(mulaw), TWILIO_MULAW_FRAME):
                frame = mulaw[offset : offset + TWILIO_MULAW_FRAME]
                if not frame:
                    continue
                await self._ws.send_text(
                    json.dumps(
                        {
                            "event": "media",
                            "streamSid": self._stream_sid,
                            "media": {
                                "payload": base64.b64encode(frame).decode(),
                            },
                        }
                    )
                )
                await asyncio.sleep(0.02)
        finally:
            self._speaking = False
