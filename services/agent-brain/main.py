import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from graph import build_graph
from session_runner import SessionRunner
from shared.clients.redis_client import RedisClient

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = RedisClient(REDIS_URL)
    graph = build_graph()
    app.state.redis = redis_client
    app.state.session_runner = SessionRunner(redis_client, graph)
    yield
    await redis_client.close()


app = FastAPI(title="agent-brain", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "agent-brain"}


@app.websocket("/ws/call/{call_sid}")
async def ws_call(websocket: WebSocket, call_sid: str):
    """Voice gateway sends final transcripts; respond with agent speech text."""
    await websocket.accept()
    session_runner: SessionRunner = websocket.app.state.session_runner

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") != "transcript" or not data.get("is_final"):
                continue

            tenant_id = data.get("tenant_id")
            if not tenant_id:
                logger.warning("transcript missing tenant_id", extra={"call_sid": call_sid})
                continue

            response_text = await session_runner.process_turn(
                tenant_id,
                call_sid,
                data["text"],
                caller_phone=data.get("caller_phone", ""),
            )
            await websocket.send_json(
                {
                    "type": "speak",
                    "text": response_text,
                    "call_sid": call_sid,
                }
            )
    except WebSocketDisconnect:
        logger.info("websocket disconnected", extra={"call_sid": call_sid})
