# services/voice-gateway/call_pipeline.py

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from agent_brain_client import AgentBrainClient
from call_session import CallSession
from livekit_bot import LiveKitBot, create_bot_token
from scripts import GREETING_TEMPLATE, format_script
from stt_client import DeepgramSTT
from tts_client import create_tts

logger = logging.getLogger(__name__)


class CallPipeline:
    """Run the full voice loop for one inbound call."""

    def __init__(
        self,
        *,
        call_sid: str,
        tenant_id: str,
        caller_phone: str,
        room_name: str,
        livekit_url: str,
        livekit_api_key: str,
        livekit_api_secret: str,
        agent_brain_url: str,
        business_name: str,
        deepgram_api_key: str,
        elevenlabs_api_key: str,
        elevenlabs_voice_id: str,
        elevenlabs_model_id: str,
        tts_provider: str = "deepgram",
        deepgram_tts_model: str = "aura-2-thalia-en",
        on_finished: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        self.call_sid = call_sid
        self.tenant_id = tenant_id
        self.caller_phone = caller_phone
        self.room_name = room_name
        self.livekit_url = livekit_url
        self.livekit_api_key = livekit_api_key
        self.livekit_api_secret = livekit_api_secret
        self.agent_brain_url = agent_brain_url
        self.business_name = business_name
        self.deepgram_api_key = deepgram_api_key
        self.elevenlabs_api_key = elevenlabs_api_key
        self.elevenlabs_voice_id = elevenlabs_voice_id
        self.elevenlabs_model_id = elevenlabs_model_id
        self.tts_provider = tts_provider
        self.deepgram_tts_model = deepgram_tts_model
        self._on_finished = on_finished
        self._stop = asyncio.Event()
        self._ready = asyncio.Event()
        self._stt_task: Optional[asyncio.Task] = None

    def stop(self) -> None:
        self._stop.set()

    async def wait_ready(self, timeout: float = 15.0) -> None:
        await asyncio.wait_for(self._ready.wait(), timeout=timeout)

    async def run(self) -> None:
        agent_client: Optional[AgentBrainClient] = None
        bot: Optional[LiveKitBot] = None

        try:
            token = create_bot_token(
                self.room_name,
                self.call_sid,
                self.livekit_api_key,
                self.livekit_api_secret,
            )
            bot = LiveKitBot(self.livekit_url, token)
            await bot.connect()

            @bot.room.on("participant_disconnected")
            def on_participant_disconnected(participant):
                if not participant.identity.startswith("bot_"):
                    self.stop()

            outbound = await bot.publish_agent_audio()
            self._ready.set()
            tts = create_tts(
                provider=self.tts_provider,
                deepgram_api_key=self.deepgram_api_key,
                deepgram_tts_model=self.deepgram_tts_model,
                elevenlabs_api_key=self.elevenlabs_api_key,
                elevenlabs_voice_id=self.elevenlabs_voice_id,
                elevenlabs_model_id=self.elevenlabs_model_id,
            )
            stt = DeepgramSTT(self.deepgram_api_key)

            agent_client = AgentBrainClient(
                self.agent_brain_url,
                self.call_sid,
                self.tenant_id,
                self.caller_phone,
            )
            await agent_client.connect()

            async def speak(text: str) -> None:
                session.is_speaking = True
                await tts.stream_to_livekit(text, outbound)
                session.is_speaking = False

            async def handle_user_turn(user_text: str) -> None:
                response = await agent_client.send_transcript(user_text)
                if response:
                    await speak(response)

            session = CallSession(
                livekit_track=outbound,
                send_to_agent=handle_user_turn,
            )

            caller_track = await bot.wait_for_caller_audio()
            logger.info(
                "caller audio connected",
                extra={"call_sid": self.call_sid, "room": self.room_name},
            )

            greeting = format_script(
                GREETING_TEMPLATE,
                business_name=self.business_name,
            )
            await speak(greeting)
            self._stt_task = asyncio.create_task(
                self._run_stt(stt, bot, caller_track, session)
            )

            await self._stop.wait()
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            if self._stop.is_set():
                logger.info(
                    "call ended before caller audio connected",
                    extra={"call_sid": self.call_sid, "tenant_id": self.tenant_id},
                )
            else:
                logger.error(
                    "caller never joined LiveKit room — check SIP dispatch rule",
                    extra={"call_sid": self.call_sid, "room": self.room_name},
                )
        except Exception:
            logger.exception(
                "call pipeline failed",
                extra={"call_sid": self.call_sid, "tenant_id": self.tenant_id},
            )
        finally:
            if self._stt_task and not self._stt_task.done():
                self._stt_task.cancel()
                try:
                    await self._stt_task
                except asyncio.CancelledError:
                    pass
            if agent_client:
                await agent_client.close()
            if bot:
                await bot.disconnect()
            if self._on_finished:
                await self._on_finished()

    async def _run_stt(
        self,
        stt: DeepgramSTT,
        bot: LiveKitBot,
        caller_track,
        session: CallSession,
    ) -> None:
        async def on_transcript(text: str, is_final: bool) -> None:
            await session.handle_transcript(text, is_final)

        await stt.stream(bot.iter_caller_audio(caller_track), on_transcript)
