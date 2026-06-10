from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from barge_in import CallSession
from stt_client import DeepgramSTT
from tts_client import ElevenLabsTTS


@pytest.fixture
def voice_gateway_client(monkeypatch):
    monkeypatch.setenv("LIVEKIT_SIP_DOMAIN", "sip.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_URL", "wss://lk.example.com")
    monkeypatch.setenv("LIVEKIT_API_KEY", "lk-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "lk-secret")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-key")

    mock_room_manager = MagicMock()
    mock_room_manager.create_call_room = AsyncMock(return_value="t_abc_CA1234567890")
    mock_room_manager.close_room = AsyncMock()

    import importlib

    import config
    import main

    importlib.reload(config)
    importlib.reload(main)

    with patch.object(main, "RoomManager", return_value=mock_room_manager):
        with TestClient(main.app) as client:
            client.mock_room_manager = mock_room_manager
            yield client


def test_incoming_call_creates_room_and_wires_pipeline(voice_gateway_client):
    response = voice_gateway_client.post(
        "/call/incoming?tenant_id=t_abc",
        data={"CallSid": "CA1234567890"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/xml")
    assert "sip:t_abc_CA1234567890@sip.livekit.cloud" in response.text

    voice_gateway_client.mock_room_manager.create_call_room.assert_awaited_once_with(
        "CA1234567890",
        "t_abc",
    )

    active_call = voice_gateway_client.app.state.active_calls["CA1234567890"]
    assert active_call["room_name"] == "t_abc_CA1234567890"
    assert active_call["tenant_id"] == "t_abc"
    assert isinstance(active_call["session"], CallSession)
    assert isinstance(active_call["stt"], DeepgramSTT)
    assert isinstance(active_call["tts"], ElevenLabsTTS)


def test_call_status_completed_closes_room(voice_gateway_client):
    voice_gateway_client.post(
        "/call/incoming?tenant_id=t_abc",
        data={"CallSid": "CA1234567890"},
    )

    response = voice_gateway_client.post(
        "/call/status?tenant_id=t_abc",
        data={"CallSid": "CA1234567890", "CallStatus": "completed"},
    )

    assert response.status_code == 204
    voice_gateway_client.mock_room_manager.close_room.assert_awaited_once_with(
        "t_abc_CA1234567890"
    )
    assert "CA1234567890" not in voice_gateway_client.app.state.active_calls
