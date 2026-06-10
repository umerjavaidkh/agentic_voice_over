# services/voice-gateway/room_manager.py

from livekit import api as livekit_api
from livekit.protocol import room as room_proto


class RoomManager:
    def __init__(self, lk_url: str, api_key: str, api_secret: str):
        self.client = livekit_api.LiveKitAPI(lk_url, api_key, api_secret)

    async def create_call_room(self, call_sid: str, tenant_id: str) -> str:
        """Create a LiveKit room for this call. Returns room name."""
        room_name = f"{tenant_id}_{call_sid}"
        await self.client.room.create_room(
            room_proto.CreateRoomRequest(
                name=room_name,
                empty_timeout=300,  # 5 min max call silence
                max_participants=2,  # caller + agent bot
            )
        )
        return room_name

    async def close_room(self, room_name: str):
        await self.client.room.delete_room(
            room_proto.DeleteRoomRequest(name=room_name)
        )
