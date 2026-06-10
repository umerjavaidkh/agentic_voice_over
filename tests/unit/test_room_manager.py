from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from room_manager import RoomManager


@pytest.mark.asyncio
async def test_create_call_room_returns_room_name():
    mock_room_service = MagicMock()
    mock_room_service.create_room = AsyncMock()
    mock_client = MagicMock()
    mock_client.room = mock_room_service

    with patch("room_manager.livekit_api.LiveKitAPI", return_value=mock_client) as mock_api:
        manager = RoomManager("wss://lk.example.com", "api-key", "api-secret")
        room_name = await manager.create_call_room("CA123456", "t_abc")

    assert room_name == "t_abc_CA123456"
    assert isinstance(room_name, str)
    mock_api.assert_called_once_with("wss://lk.example.com", "api-key", "api-secret")
    mock_room_service.create_room.assert_awaited_once()
    request = mock_room_service.create_room.call_args[0][0]
    assert request.name == "t_abc_CA123456"
    assert request.empty_timeout == 300
    assert request.max_participants == 2
