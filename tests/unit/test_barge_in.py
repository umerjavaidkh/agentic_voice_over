from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from barge_in import CallSession


@pytest.mark.asyncio
async def test_barge_in_cancels_tts_when_speaking_and_not_final():
    mock_track = MagicMock()
    mock_track.send_silence = AsyncMock()

    mock_tts_stream = AsyncMock()

    session = CallSession(livekit_track=mock_track)
    session.is_speaking = True
    session.tts_stream = mock_tts_stream

    with patch.object(session, "cancel_tts", wraps=session.cancel_tts) as cancel_tts:
        with patch.object(session, "send_to_agent", new_callable=AsyncMock) as send_to_agent:
            await session.handle_transcript("wait hold on", is_final=False)

    cancel_tts.assert_awaited_once()
    mock_tts_stream.aclose.assert_awaited_once()
    assert session.tts_stream is None
    assert session.is_speaking is False
    mock_track.send_silence.assert_awaited_once()
    send_to_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_final_transcript_sent_to_agent_when_not_barging_in():
    session = CallSession()

    with patch.object(session, "send_to_agent", new_callable=AsyncMock) as send_to_agent:
        with patch.object(session, "cancel_tts", new_callable=AsyncMock) as cancel_tts:
            await session.handle_transcript("my water heater is leaking", is_final=True)

    cancel_tts.assert_not_awaited()
    send_to_agent.assert_awaited_once_with("my water heater is leaking")
