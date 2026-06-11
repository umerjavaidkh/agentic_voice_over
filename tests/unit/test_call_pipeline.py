from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from call_pipeline import CallPipeline


@pytest.fixture
def pipeline():
    return CallPipeline(
        call_sid="CA123",
        tenant_id="t_abc",
        caller_phone="+15551234567",
        room_name="t_abc_CA123",
        livekit_url="wss://lk.example.com",
        livekit_api_key="lk-key",
        livekit_api_secret="lk-secret",
        agent_brain_url="http://agent-brain:8001",
        business_name="Test Plumbing",
        deepgram_api_key="dg-key",
        elevenlabs_api_key="el-key",
        elevenlabs_voice_id="voice-id",
        elevenlabs_model_id="model-id",
    )


@pytest.mark.asyncio
async def test_pipeline_plays_greeting_and_forwards_transcript(pipeline):
    mock_bot = MagicMock()
    mock_bot.connect = AsyncMock()
    mock_bot.disconnect = AsyncMock()
    mock_bot.publish_agent_audio = AsyncMock(return_value=MagicMock())
    mock_bot.wait_for_caller_audio = AsyncMock(return_value=MagicMock())
    mock_bot.iter_caller_audio = MagicMock(return_value=_empty_audio())
    mock_bot.room = MagicMock()
    mock_bot.room.on = MagicMock(return_value=lambda _fn: _fn)

    mock_agent = MagicMock()
    mock_agent.connect = AsyncMock()
    mock_agent.close = AsyncMock()
    mock_agent.send_transcript = AsyncMock(return_value="I can help with that.")

    mock_tts = MagicMock()
    mock_tts.stream_to_livekit = AsyncMock()

    async def stt_then_stop(_audio, on_transcript):
        await on_transcript("leaking pipe", is_final=True)
        pipeline.stop()

    mock_stt = MagicMock()
    mock_stt.stream = AsyncMock(side_effect=stt_then_stop)

    with (
        patch("call_pipeline.create_bot_token", return_value="token"),
        patch("call_pipeline.LiveKitBot", return_value=mock_bot),
        patch("call_pipeline.AgentBrainClient", return_value=mock_agent),
        patch("call_pipeline.ElevenLabsTTS", return_value=mock_tts),
        patch("call_pipeline.DeepgramSTT", return_value=mock_stt),
    ):
        await pipeline.run()

    assert mock_agent.connect.await_count == 1
    greeting_call = mock_tts.stream_to_livekit.await_args_list[0]
    assert "Test Plumbing" in greeting_call.args[0]
    mock_stt.stream.assert_awaited_once()
    mock_agent.send_transcript.assert_awaited_once_with("leaking pipe")


async def _empty_audio():
    if False:
        yield None
