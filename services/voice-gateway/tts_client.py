# services/voice-gateway/tts_client.py

from collections.abc import AsyncIterator, Iterable, Iterator
from typing import Union

from elevenlabs import ElevenLabs, VoiceSettings

AudioStream = Union[AsyncIterator[bytes], Iterator[bytes], Iterable[bytes]]


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

    def __init__(self, api_key: str):
        self.client = ElevenLabs(api_key=api_key)
        if not hasattr(self.client.text_to_speech, "convert_as_stream"):
            self.client.text_to_speech.convert_as_stream = (
                self.client.text_to_speech.stream
            )

    async def stream_to_livekit(self, text: str, lk_audio_track):
        """Stream TTS audio chunks directly into LiveKit track."""
        audio_stream = self.client.text_to_speech.convert_as_stream(
            voice_id=self.VOICE_ID,
            text=text,
            model_id=self.MODEL_ID,
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
