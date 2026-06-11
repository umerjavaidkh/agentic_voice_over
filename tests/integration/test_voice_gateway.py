import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit" / "voice_gateway"))
from voice_gateway_loader import load_voice_gateway_main


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

    mock_redis = MagicMock()
    mock_redis.set_call_meta = AsyncMock()
    mock_redis.get_call_meta = AsyncMock(return_value={"tenant_id": "t_abc"})
    mock_redis.close = AsyncMock()

    mock_db = MagicMock()
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_db.connect = AsyncMock()
    mock_db.close = AsyncMock()

    main = load_voice_gateway_main()

    mock_pipeline = MagicMock()
    mock_pipeline.run = AsyncMock()
    mock_pipeline.stop = MagicMock()

    with (
        patch.object(main, "RoomManager", return_value=mock_room_manager),
        patch.object(main, "RedisClient", return_value=mock_redis),
        patch.object(main, "DatabasePool", return_value=mock_db),
        patch.object(main, "CallPipeline", return_value=mock_pipeline),
    ):
        with TestClient(main.app) as client:
            client.mock_room_manager = mock_room_manager
            client.mock_redis = mock_redis
            client.mock_db = mock_db
            client.mock_conn = mock_conn
            client.voice_gateway_main = main
            yield client


def test_incoming_call_creates_room_and_wires_pipeline(voice_gateway_client):
    main = sys.modules["voice_gateway_main"]

    response = voice_gateway_client.post(
        "/call/incoming?tenant_id=t_abc",
        data={"CallSid": "CA1234567890", "From": "+15551234567"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/xml")
    assert "sip:t_abc_CA1234567890@sip.livekit.cloud" in response.text

    voice_gateway_client.mock_room_manager.create_call_room.assert_awaited_once_with(
        "CA1234567890",
        "t_abc",
    )
    voice_gateway_client.mock_redis.set_call_meta.assert_awaited_once()
    voice_gateway_client.mock_conn.execute.assert_awaited_once()
    main.CallPipeline.assert_called_once()

    active_call = voice_gateway_client.app.state.active_calls["CA1234567890"]
    assert active_call["room_name"] == "t_abc_CA1234567890"
    assert active_call["tenant_id"] == "t_abc"
    assert "pipeline" in active_call
    assert "pipeline_task" in active_call


def test_call_status_completed_closes_room(voice_gateway_client):
    voice_gateway_client.post(
        "/call/incoming?tenant_id=t_abc",
        data={"CallSid": "CA1234567890", "From": "+15551234567"},
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


def test_call_recording_finalizes_call(voice_gateway_client):
    voice_gateway_client.post(
        "/call/incoming?tenant_id=t_abc",
        data={"CallSid": "CA1234567890", "From": "+15551234567"},
    )

    main = voice_gateway_client.voice_gateway_main
    with (
        patch.object(
            main,
            "download_twilio_recording",
            new_callable=AsyncMock,
            return_value=b"recording-bytes",
        ) as download_recording,
        patch.object(main, "finalize_call", new_callable=AsyncMock) as finalize_call,
    ):
        response = voice_gateway_client.post(
            "/call/recording?tenant_id=t_abc",
            data={
                "CallSid": "CA1234567890",
                "RecordingUrl": "https://api.twilio.com/recording/RE123",
                "RecordingSid": "RE123",
            },
        )

    assert response.status_code == 204
    download_recording.assert_awaited_once()
    finalize_call.assert_awaited_once_with(
        "CA1234567890",
        "t_abc",
        b"recording-bytes",
        voice_gateway_client.mock_db,
    )
