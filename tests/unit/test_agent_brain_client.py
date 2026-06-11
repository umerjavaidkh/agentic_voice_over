import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_brain_client import AgentBrainClient, to_websocket_url


def test_to_websocket_url_converts_http_to_ws():
    assert (
        to_websocket_url("http://agent-brain:8001", "/ws/call/CA123")
        == "ws://agent-brain:8001/ws/call/CA123"
    )


def test_to_websocket_url_converts_https_to_wss():
    assert (
        to_websocket_url("https://agent-brain:8001", "/ws/call/CA123")
        == "wss://agent-brain:8001/ws/call/CA123"
    )


@pytest.mark.asyncio
async def test_send_transcript_returns_speak_text():
    mock_ws = AsyncMock()
    mock_ws.recv = AsyncMock(
        return_value=json.dumps({"type": "speak", "text": "What is your address?"})
    )

    with patch("agent_brain_client.websockets.connect", new_callable=AsyncMock, return_value=mock_ws):
        client = AgentBrainClient(
            "http://agent-brain:8001",
            "CA123",
            "t_abc",
            "+15551234567",
        )
        await client.connect()
        response = await client.send_transcript("water heater leaking")

    assert response == "What is your address?"
    mock_ws.send.assert_awaited_once()
    sent = json.loads(mock_ws.send.await_args.args[0])
    assert sent["type"] == "transcript"
    assert sent["is_final"] is True
    assert sent["tenant_id"] == "t_abc"
    await client.close()
