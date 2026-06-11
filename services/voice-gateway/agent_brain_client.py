# services/voice-gateway/agent_brain_client.py

import json
import logging
from typing import Optional

import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)


def to_websocket_url(base_url: str, path: str) -> str:
    """Convert http(s) service URL to ws(s) for WebSocket connections."""
    if base_url.startswith("https://"):
        ws_base = "wss://" + base_url[len("https://") :]
    elif base_url.startswith("http://"):
        ws_base = "ws://" + base_url[len("http://") :]
    elif base_url.startswith("ws://") or base_url.startswith("wss://"):
        ws_base = base_url
    else:
        ws_base = "ws://" + base_url
    return ws_base.rstrip("/") + path


class AgentBrainClient:
    """Persistent WebSocket client for one call session with agent-brain."""

    def __init__(
        self,
        base_url: str,
        call_sid: str,
        tenant_id: str,
        caller_phone: str = "",
    ):
        self.base_url = base_url
        self.call_sid = call_sid
        self.tenant_id = tenant_id
        self.caller_phone = caller_phone
        self._ws: Optional[ClientConnection] = None

    async def connect(self) -> None:
        url = to_websocket_url(self.base_url, f"/ws/call/{self.call_sid}")
        self._ws = await websockets.connect(url)
        logger.info(
            "connected to agent-brain",
            extra={"call_sid": self.call_sid, "tenant_id": self.tenant_id},
        )

    async def send_transcript(self, text: str) -> Optional[str]:
        """Send a final transcript and wait for the agent speak response."""
        if not self._ws:
            raise RuntimeError("AgentBrainClient is not connected")

        await self._ws.send(
            json.dumps(
                {
                    "type": "transcript",
                    "call_sid": self.call_sid,
                    "tenant_id": self.tenant_id,
                    "caller_phone": self.caller_phone,
                    "text": text,
                    "is_final": True,
                }
            )
        )

        raw = await self._ws.recv()
        message = json.loads(raw)
        if message.get("type") == "speak":
            return message.get("text")
        return None

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None
