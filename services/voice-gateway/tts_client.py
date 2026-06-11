# services/voice-gateway/tts_client.py

from collections.abc import AsyncIterator, Iterable, Iterator
from typing import Protocol, Union

import httpx
from elevenlabs import ElevenLabs, VoiceSettings

AudioStream = Union[AsyncIterator[bytes], Iterator[bytes], Iterable[bytes]]

PCM_CHUNK_SIZE = 3200  # 100ms @ 16kHz mono 16-bit


class TextToSpeech(Protocol):
    async def stream_to_livekit(self, text: str, lk_audio_track) -> None: ...

    async def synthesize_pcm16(self, text: str) -> bytes: ...


async def _iter_audio_chunks(audio_stream: AudioStream) -> AsyncIterator[bytes]:
    if hasattr(audio_stream, "__aiter__"):
        async for chunk in audio_stream:
            yield chunk
    else:
        for chunk in audio_stream:
            yield chunk


class ElevenLabsTTS:
    VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Professional, warm male voice
    MODEL_ID = "eleven_turbo_v2_5"  # Lowest latency model

    def __init__(
        self,
        api_key: str,
        voice_id: str | None = None,
        model_id: str | None = None,
    ):
        self.voice_id = voice_id or self.VOICE_ID
        self.model_id = model_id or self.MODEL_ID
        self.client = ElevenLabs(api_key=api_key)
        if not hasattr(self.client.text_to_speech, "convert_as_stream"):
            self.client.text_to_speech.convert_as_stream = (
                self.client.text_to_speech.stream
            )

    async def stream_to_livekit(self, text: str, lk_audio_track):
        """Stream TTS audio chunks directly into LiveKit track."""
        audio_stream = self.client.text_to_speech.convert_as_stream(
            voice_id=self.voice_id,
            text=text,
            model_id=self.model_id,
            voice_settings=VoiceSettings(
                stability=0.6,
                similarity_boost=0.85,
                style=0.2,
                use_speaker_boost=True,
            ),
            output_format="pcm_16000",  # Raw PCM, no decode overhead
        )

        async for chunk in _iter_audio_chunks(audio_stream):
            if chunk:
                await lk_audio_track.write_sample(chunk)

    async def synthesize_pcm16(self, text: str) -> bytes:
        chunks: list[bytes] = []
        audio_stream = self.client.text_to_speech.convert_as_stream(
            voice_id=self.voice_id,
            text=text,
            model_id=self.model_id,
            voice_settings=VoiceSettings(
                stability=0.6,
                similarity_boost=0.85,
                style=0.2,
                use_speaker_boost=True,
            ),
            output_format="pcm_16000",
        )
        async for chunk in _iter_audio_chunks(audio_stream):
            if chunk:
                chunks.append(chunk)
        return b"".join(chunks)


class DeepgramTTS:
    """Deepgram Aura TTS — works on free tier (unlike ElevenLabs library voices)."""

    def __init__(self, api_key: str, model: str = "aura-2-thalia-en"):
        self.api_key = api_key
        self.model = model

    async def stream_to_livekit(self, text: str, lk_audio_track) -> None:
        url = (
            "https://api.deepgram.com/v1/speak"
            f"?model={self.model}&encoding=linear16&sample_rate=16000&container=none"
        )
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Token {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": text},
                timeout=30.0,
            )
            response.raise_for_status()
            pcm = response.content

        for offset in range(0, len(pcm), PCM_CHUNK_SIZE):
            chunk = pcm[offset : offset + PCM_CHUNK_SIZE]
            if chunk:
                await lk_audio_track.write_sample(chunk)

    async def synthesize_pcm16(self, text: str) -> bytes:
        url = (
            "https://api.deepgram.com/v1/speak"
            f"?model={self.model}&encoding=linear16&sample_rate=16000&container=none"
        )
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Token {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": text},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.content


def create_tts(
    *,
    provider: str,
    deepgram_api_key: str,
    deepgram_tts_model: str,
    elevenlabs_api_key: str,
    elevenlabs_voice_id: str,
    elevenlabs_model_id: str,
) -> TextToSpeech:
    if provider == "elevenlabs":
        return ElevenLabsTTS(
            elevenlabs_api_key,
            voice_id=elevenlabs_voice_id,
            model_id=elevenlabs_model_id,
        )
    return DeepgramTTS(deepgram_api_key, model=deepgram_tts_model)
