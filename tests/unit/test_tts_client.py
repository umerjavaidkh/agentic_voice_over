from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from elevenlabs import VoiceSettings

from tts_client import ElevenLabsTTS


async def _mock_audio_stream():
    yield b"pcm-chunk-1"
    yield b"pcm-chunk-2"


@pytest.mark.asyncio
async def test_stream_to_livekit_writes_chunks_to_audio_track():
    mock_track = MagicMock()
    mock_track.write_sample = AsyncMock()

    mock_tts = MagicMock()
    mock_tts.convert_as_stream.return_value = _mock_audio_stream()
    mock_client = MagicMock()
    mock_client.text_to_speech = mock_tts

    with patch("tts_client.ElevenLabs", return_value=mock_client):
        tts = ElevenLabsTTS("test-api-key")
        await tts.stream_to_livekit("Hello from the agent", mock_track)

    mock_tts.convert_as_stream.assert_called_once_with(
        voice_id=ElevenLabsTTS.VOICE_ID,
        text="Hello from the agent",
        model_id=ElevenLabsTTS.MODEL_ID,
        voice_settings=VoiceSettings(
            stability=0.6,
            similarity_boost=0.85,
            style=0.2,
            use_speaker_boost=True,
        ),
        output_format="pcm_16000",
    )
    mock_track.write_sample.assert_any_await(b"pcm-chunk-1")
    mock_track.write_sample.assert_any_await(b"pcm-chunk-2")
    assert mock_track.write_sample.await_count == 2
