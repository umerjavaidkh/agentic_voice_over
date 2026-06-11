import pytest
from fastapi.testclient import TestClient

from twilio_sip import handle_incoming
from voice_gateway_loader import load_voice_gateway_main


def test_handle_incoming_builds_sip_dial_twiml():
    twiml = handle_incoming(
        call_sid="CA1234567890",
        tenant_id="t_abc",
        livekit_sip_domain="sip.livekit.cloud",
    )

    assert "sip:t_abc_CA1234567890@sip.livekit.cloud;transport=tls" in twiml
    assert "<Dial>" in twiml
    assert "<Sip>" in twiml


@pytest.fixture
def client(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock, patch

    monkeypatch.setenv("LIVEKIT_SIP_DOMAIN", "sip.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_URL", "wss://lk.example.com")
    monkeypatch.setenv("LIVEKIT_API_KEY", "lk-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "lk-secret")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-key")

    main = load_voice_gateway_main()

    mock_room_manager = MagicMock()
    mock_room_manager.create_call_room = AsyncMock(
        return_value=("t_abc_CA1234567890", "SDR_test")
    )
    mock_room_manager.close_room = AsyncMock()

    mock_redis = MagicMock()
    mock_redis.set_call_meta = AsyncMock()
    mock_redis.get_call_meta = AsyncMock(return_value=None)
    mock_redis.close = AsyncMock()

    mock_db = MagicMock()
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_db.connect = AsyncMock()
    mock_db.close = AsyncMock()

    mock_pipeline = MagicMock()
    mock_pipeline.run = AsyncMock()
    mock_pipeline.stop = MagicMock()
    mock_pipeline.wait_ready = AsyncMock()

    with (
        patch.object(main, "RoomManager", return_value=mock_room_manager),
        patch.object(main, "RedisClient", return_value=mock_redis),
        patch.object(main, "DatabasePool", return_value=mock_db),
        patch.object(main, "CallPipeline", return_value=mock_pipeline),
    ):
        with TestClient(main.app) as test_client:
            yield test_client


def test_call_incoming_returns_twiml(client):
    response = client.post(
        "/call/incoming?tenant_id=t_abc",
        data={"CallSid": "CA1234567890", "From": "+15551234567"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/xml")
    assert "sip:t_abc_CA1234567890@sip.livekit.cloud;transport=tls" in response.text


def test_call_incoming_requires_tenant_id(client):
    response = client.post(
        "/call/incoming",
        data={"CallSid": "CA1234567890"},
    )

    assert response.status_code == 422


def test_call_incoming_503_when_sip_domain_missing():
    from unittest.mock import AsyncMock, MagicMock, patch

    main = load_voice_gateway_main()

    mock_room_manager = MagicMock()
    mock_room_manager.create_call_room = AsyncMock()

    mock_redis = MagicMock()
    mock_redis.close = AsyncMock()
    mock_db = MagicMock()
    mock_db.connect = AsyncMock()
    mock_db.close = AsyncMock()

    with (
        patch.object(main, "RoomManager", return_value=mock_room_manager),
        patch.object(main, "RedisClient", return_value=mock_redis),
        patch.object(main, "DatabasePool", return_value=mock_db),
        patch.object(main.settings, "livekit_sip_domain", ""),
    ):
        with TestClient(main.app) as client:
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
