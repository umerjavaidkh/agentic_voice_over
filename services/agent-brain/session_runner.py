# services/agent-brain/session_runner.py

from shared.clients.redis_client import RedisClient
from shared.models.agent_state import AgentState


class SessionRunner:
    def __init__(self, redis_client: RedisClient, graph):
        self.redis = redis_client
        self.graph = graph

    async def process_turn(
        self,
        tenant_id: str,
        call_sid: str,
        user_text: str,
        caller_phone: str = "",
    ) -> str:
        # Load state from Redis
        state_dict = await self.redis.get_call_state(tenant_id, call_sid)
        if state_dict:
            state = AgentState(**state_dict)
        else:
            state = AgentState(
                call_sid=call_sid,
                tenant_id=tenant_id,
                caller_phone=caller_phone,
            )

        # Append new user turn
        state.conversation_history.append({"role": "user", "content": user_text})
        state.turn_count += 1

        # Run graph
        result_state = await self.graph.ainvoke(state)
        if isinstance(result_state, dict):
            result_state = AgentState(**result_state)

        # Persist updated state
        await self.redis.set_call_state(
            tenant_id,
            call_sid,
            result_state.model_dump(),
            ttl=1800,  # 30 min TTL
        )

        return result_state.agent_response
