# services/voice-gateway/room_manager.py

import logging

from livekit import api as livekit_api
from livekit.api.twirp_client import TwirpError
from livekit.protocol import room as room_proto
from livekit.protocol.sip import (
    CreateSIPDispatchRuleRequest,
    DeleteSIPDispatchRuleRequest,
    ListSIPDispatchRuleRequest,
    SIPDispatchRule,
    SIPDispatchRuleDirect,
)

logger = logging.getLogger(__name__)


class RoomManager:
    def __init__(
        self,
        lk_url: str,
        api_key: str,
        api_secret: str,
        sip_trunk_id: str = "",
    ):
        api_url = lk_url.replace("wss://", "https://").replace("ws://", "http://")
        self.client = livekit_api.LiveKitAPI(api_url, api_key, api_secret)
        self.sip_trunk_id = sip_trunk_id

    def _dispatch_rule_name(self, call_sid: str) -> str:
        return f"call_{call_sid}"

    async def _delete_dispatch_rules_for_call(self, call_sid: str) -> None:
        target_name = self._dispatch_rule_name(call_sid)
        rules = await self.client.sip.list_sip_dispatch_rule(
            ListSIPDispatchRuleRequest()
        )
        for rule in rules.items:
            if rule.name == target_name:
                await self.client.sip.delete_sip_dispatch_rule(
                    DeleteSIPDispatchRuleRequest(
                        sip_dispatch_rule_id=rule.sip_dispatch_rule_id,
                    )
                )
                logger.info(
                    "deleted stale sip dispatch rule",
                    extra={
                        "call_sid": call_sid,
                        "dispatch_rule_id": rule.sip_dispatch_rule_id,
                    },
                )

    async def _find_dispatch_rule_id(self, call_sid: str) -> str:
        target_name = self._dispatch_rule_name(call_sid)
        rules = await self.client.sip.list_sip_dispatch_rule(
            ListSIPDispatchRuleRequest()
        )
        for rule in rules.items:
            if rule.name == target_name:
                return rule.sip_dispatch_rule_id
        return ""

    async def create_call_room(self, call_sid: str, tenant_id: str) -> tuple[str, str]:
        """Create a LiveKit room and per-call SIP dispatch rule. Returns (room_name, dispatch_rule_id)."""
        room_name = f"{tenant_id}_{call_sid}"
        try:
            await self.client.room.create_room(
                room_proto.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=300,
                    max_participants=2,
                )
            )
        except TwirpError as exc:
            if exc.code != "already_exists":
                raise
            logger.info(
                "livekit room already exists",
                extra={"call_sid": call_sid, "room_name": room_name},
            )

        dispatch_rule_id = ""
        if self.sip_trunk_id:
            await self._delete_dispatch_rules_for_call(call_sid)
            try:
                rule = await self.client.sip.create_sip_dispatch_rule(
                    CreateSIPDispatchRuleRequest(
                        name=self._dispatch_rule_name(call_sid),
                        trunk_ids=[self.sip_trunk_id],
                        rule=SIPDispatchRule(
                            dispatch_rule_direct=SIPDispatchRuleDirect(
                                room_name=room_name,
                            )
                        ),
                    )
                )
                dispatch_rule_id = rule.sip_dispatch_rule_id
            except TwirpError as exc:
                if "already exists" not in (exc.message or ""):
                    raise
                dispatch_rule_id = await self._find_dispatch_rule_id(call_sid)
                if not dispatch_rule_id:
                    raise
                logger.info(
                    "reusing existing sip dispatch rule",
                    extra={
                        "call_sid": call_sid,
                        "dispatch_rule_id": dispatch_rule_id,
                    },
                )

            logger.info(
                "sip dispatch rule ready",
                extra={
                    "call_sid": call_sid,
                    "room_name": room_name,
                    "dispatch_rule_id": dispatch_rule_id,
                },
            )

        return room_name, dispatch_rule_id

    async def close_room(self, room_name: str, dispatch_rule_id: str = "") -> None:
        if dispatch_rule_id:
            try:
                await self.client.sip.delete_sip_dispatch_rule(
                    DeleteSIPDispatchRuleRequest(
                        sip_dispatch_rule_id=dispatch_rule_id,
                    )
                )
            except Exception:
                logger.exception(
                    "failed to delete sip dispatch rule",
                    extra={"dispatch_rule_id": dispatch_rule_id, "room_name": room_name},
                )

        try:
            await self.client.room.delete_room(
                room_proto.DeleteRoomRequest(name=room_name)
            )
        except TwirpError as exc:
            if exc.code != "not_found":
                raise
