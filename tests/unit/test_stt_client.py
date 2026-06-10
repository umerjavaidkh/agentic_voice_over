from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from deepgram import LiveTranscriptionEvents

from stt_client import DeepgramSTT


async def _mock_audio_track():
    chunk = MagicMock()
    chunk.data = b"\x00\x01" * 80
    yield chunk


@pytest.mark.asyncio
async def test_stream_fires_callback_on_final_transcript():
    transcript_calls = []

    async def on_transcript(text: str, is_final: bool):
        transcript_calls.append((text, is_final))

    mock_connection = MagicMock()
    mock_connection.send = AsyncMock()
    transcript_handlers = []

    def register_handler(event, handler):
        if event == LiveTranscriptionEvents.Transcript:
            transcript_handlers.append(handler)

    mock_connection.on = register_handler

    async def start_and_emit_transcript(options):
        result = MagicMock()
        result.channel.alternatives = [MagicMock(transcript="water heater leak")]
        result.is_final = True
        await transcript_handlers[0](None, result)
        return True

    mock_connection.start = AsyncMock(side_effect=start_and_emit_transcript)

    mock_asynclive = MagicMock()
    mock_asynclive.v.return_value = mock_connection
    mock_client = MagicMock()
    mock_client.listen.asynclive = mock_asynclive

    with patch("stt_client.DeepgramClient", return_value=mock_client):
        stt = DeepgramSTT("test-api-key")
        await stt.stream(_mock_audio_track(), on_transcript)

    assert transcript_calls == [("water heater leak", True)]
    mock_connection.start.assert_awaited_once()
    mock_connection.send.assert_awaited_once_with(b"\x00\x01" * 80)
