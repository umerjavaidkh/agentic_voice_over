# services/voice-gateway/livekit_bot.py

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from livekit import api, rtc

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
NUM_CHANNELS = 1


def create_bot_token(
    room_name: str,
    call_sid: str,
    api_key: str,
    api_secret: str,
) -> str:
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(f"bot_{call_sid}")
        .with_name("voice-agent-bot")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )


@dataclass
class AudioChunk:
    data: bytes


class OutboundAudioTrack:
    """Adapter so ElevenLabsTTS can publish PCM into a LiveKit room."""

    def __init__(self, source: rtc.AudioSource):
        self._source = source

    async def write_sample(self, pcm: bytes) -> None:
        if not pcm:
            return
        samples_per_channel = len(pcm) // (2 * NUM_CHANNELS)
        frame = rtc.AudioFrame(
            data=pcm,
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            samples_per_channel=samples_per_channel,
        )
        await self._source.capture_frame(frame)

    async def send_silence(self, duration_ms: int = 100) -> None:
        samples = int(SAMPLE_RATE * duration_ms / 1000)
        await self.write_sample(b"\x00\x00" * samples)


class LiveKitBot:
    """Join a LiveKit room as the voice-agent bot participant."""

    def __init__(self, livekit_url: str, token: str):
        self._url = livekit_url
        self._token = token
        self._room = rtc.Room()
        self._caller_audio: Optional[asyncio.Future] = None

        @self._room.on("track_subscribed")
        def on_track_subscribed(
            track: rtc.Track,
            _publication: rtc.RemoteTrackPublication,
            participant: rtc.RemoteParticipant,
        ):
            if (
                track.kind == rtc.TrackKind.KIND_AUDIO
                and not participant.identity.startswith("bot_")
                and self._caller_audio is not None
                and not self._caller_audio.done()
            ):
                self._caller_audio.set_result(track)

    @property
    def room(self) -> rtc.Room:
        return self._room

    async def connect(self) -> None:
        self._caller_audio = asyncio.get_running_loop().create_future()
        await self._room.connect(self._url, self._token)
        logger.info("livekit bot connected", extra={"room": self._room.name})

    async def publish_agent_audio(self) -> OutboundAudioTrack:
        source = rtc.AudioSource(SAMPLE_RATE, NUM_CHANNELS)
        track = rtc.LocalAudioTrack.create_audio_track("agent-voice", source)
        await self._room.local_participant.publish_track(
            track,
            rtc.TrackPublishOptions(),
        )
        return OutboundAudioTrack(source)

    async def wait_for_caller_audio(self, timeout: float = 120.0) -> rtc.RemoteAudioTrack:
        if self._caller_audio is None:
            raise RuntimeError("LiveKitBot.connect() must be called first")
        return await asyncio.wait_for(self._caller_audio, timeout=timeout)

    async def iter_caller_audio(self, track: rtc.RemoteAudioTrack):
        """Yield audio chunks compatible with DeepgramSTT.stream()."""
        stream = rtc.AudioStream(track)
        async for event in stream:
            yield AudioChunk(data=bytes(event.frame.data))

    async def disconnect(self) -> None:
        await self._room.disconnect()
