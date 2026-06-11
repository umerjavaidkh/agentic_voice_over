from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from call_finisher import create_blob_service_client, date_path, download_twilio_recording, finalize_call


def test_date_path_uses_utc_yyyy_mm_dd():
    from datetime import datetime, timezone

    with patch("call_finisher.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2026, 6, 10, tzinfo=timezone.utc)
        mock_datetime.timezone = timezone
        assert date_path() == "2026/06/10"


def test_create_blob_service_client_uses_connection_string_when_set(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    with patch("call_finisher.BlobServiceClient.from_connection_string") as from_conn:
        from_conn.return_value = MagicMock()
        create_blob_service_client()
    from_conn.assert_called_once_with("UseDevelopmentStorage=true")


@pytest.mark.asyncio
async def test_download_twilio_recording_appends_mp3_and_uses_auth():
    mock_response = MagicMock()
    mock_response.content = b"audio-bytes"
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("call_finisher.httpx.AsyncClient", return_value=mock_client):
        data = await download_twilio_recording(
            "https://api.twilio.com/recording/RE123",
            "AC-test",
            "token-test",
        )

    assert data == b"audio-bytes"
    mock_client.get.assert_awaited_once_with(
        "https://api.twilio.com/recording/RE123.mp3",
        auth=("AC-test", "token-test"),
    )


@pytest.mark.asyncio
async def test_finalize_call_uploads_blob_and_updates_db():
    mock_blob_service = MagicMock()
    mock_container = MagicMock()
    mock_container.upload_blob = AsyncMock()
    mock_blob_service.get_container_client.return_value = mock_container
    mock_blob_service.close = AsyncMock()

    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_db = MagicMock()
    mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("call_finisher.create_blob_service_client", return_value=mock_blob_service),
        patch("call_finisher.date_path", return_value="2026/06/10"),
    ):
        await finalize_call("CA123", "t_abc", b"mp3-bytes", mock_db)

    mock_container.upload_blob.assert_awaited_once()
    upload_kwargs = mock_container.upload_blob.await_args.kwargs
    assert upload_kwargs["name"] == "t_abc/2026/06/10/CA123.mp3"
    assert upload_kwargs["data"] == b"mp3-bytes"
    mock_conn.execute.assert_awaited_once()
    mock_blob_service.close.assert_awaited_once()
