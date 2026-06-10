import os

import pytest
from fastapi.testclient import TestClient

from twilio_sip import handle_incoming


def test_handle_incoming_builds_sip_dial_twiml():
    twiml = handle_incoming(
        call_sid="CA1234567890",
        tenant_id="t_abc",
        livekit_sip_domain="sip.livekit.cloud",
    )

    assert 'sip:t_abc_CA1234567890@sip.livekit.cloud' in twiml
    assert "<Dial>" in twiml
    assert "<Sip>" in twiml


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LIVEKIT_SIP_DOMAIN", "sip.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_URL", "wss://lk.example.com")
    monkeypatch.setenv("LIVEKIT_API_KEY", "lk-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "lk-secret")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-key")

    import importlib
    from unittest.mock import AsyncMock, MagicMock, patch

    import config
    import main

    importlib.reload(config)
    importlib.reload(main)

    mock_room_manager = MagicMock()
    mock_room_manager.create_call_room = AsyncMock(return_value="t_abc_CA1234567890")
    mock_room_manager.close_room = AsyncMock()

    with patch.object(main, "RoomManager", return_value=mock_room_manager):
        with TestClient(main.app) as test_client:
            yield test_client


def test_call_incoming_returns_twiml(client):
    response = client.post(
        "/call/incoming?tenant_id=t_abc",
        data={"CallSid": "CA1234567890"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/xml")
    assert "sip:t_abc_CA1234567890@sip.livekit.cloud" in response.text


def test_call_incoming_requires_tenant_id(client):
    response = client.post(
        "/call/incoming",
        data={"CallSid": "CA1234567890"},
    )

    assert response.status_code == 422


def test_call_incoming_503_when_sip_domain_missing(monkeypatch):
    monkeypatch.delenv("LIVEKIT_SIP_DOMAIN", raising=False)
    import importlib
    from unittest.mock import AsyncMock, MagicMock, patch

    import config
    import main

    importlib.reload(config)
    importlib.reload(main)

    mock_room_manager = MagicMock()
    mock_room_manager.create_call_room = AsyncMock()
    with patch.object(main, "RoomManager", return_value=mock_room_manager):
        client = TestClient(main.app)

    response = client.post(
        "/call/incoming?tenant_id=t_abc",
        data={"CallSid": "CA1234567890"},
    )

    assert response.status_code == 503


def test_call_status_returns_204(client):
    response = client.post(
        "/call/status?tenant_id=t_abc",
        data={"CallSid": "CA1234567890", "CallStatus": "completed"},
    )

    assert response.status_code == 204


def test_call_recording_returns_204(client):
    response = client.post(
        "/call/recording?tenant_id=t_abc",
        data={
            "CallSid": "CA1234567890",
            "RecordingUrl": "https://api.twilio.com/recording.mp3",
            "RecordingSid": "RE123",
        },
    )

    assert response.status_code == 204
