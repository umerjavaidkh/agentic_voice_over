#!/usr/bin/env python3
"""Prepare LiveKit SIP for Twilio <Dial><Sip>sip:{room}@{domain}</Sip> routing.

Per-call direct dispatch rules are created by voice-gateway/room_manager.py.
This script removes stale global rules and relaxes the inbound trunk number filter
so Twilio can dial dynamic room names (t_test_CA...) instead of only +1XXXXXXXXXX.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from livekit import api
from livekit.protocol.sip import (
    DeleteSIPDispatchRuleRequest,
    ListSIPDispatchRuleRequest,
    ListSIPInboundTrunkRequest,
    SIPInboundTrunkInfo,
)

# Twilio US signaling IP ranges — tighten in production
TWILIO_SIG_IPS = [
    "54.172.60.0/30",
    "54.244.51.0/24",
    "177.71.206.0/24",
]


def _livekit_api() -> api.LiveKitAPI:
    url = os.environ.get("LIVEKIT_URL", "").replace("wss://", "https://")
    return api.LiveKitAPI(
        url=url,
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )


async def _run(trunk_id: str | None, dry_run: bool) -> None:
    lk = _livekit_api()
    try:
        trunks = await lk.sip.list_sip_inbound_trunk(ListSIPInboundTrunkRequest())
        if not trunks.items:
            raise SystemExit("No inbound SIP trunks found in LiveKit project")

        trunk = trunks.items[0]
        if trunk_id is None:
            trunk_id = trunk.sip_trunk_id
        print(f"Trunk: {trunk.name} ({trunk_id}) numbers={list(trunk.numbers)}")

        rules = await lk.sip.list_sip_dispatch_rule(ListSIPDispatchRuleRequest())
        print(f"\nFound {len(rules.items)} global dispatch rule(s)")
        for rule in rules.items:
            print(f"  {rule.name} ({rule.sip_dispatch_rule_id}) -> {rule.rule}")
            if not dry_run:
                await lk.sip.delete_sip_dispatch_rule(
                    DeleteSIPDispatchRuleRequest(
                        sip_dispatch_rule_id=rule.sip_dispatch_rule_id
                    )
                )
                print("    deleted")

        if dry_run:
            print("\nDry run — would set numbers=['*'] and Twilio signaling IPs")
            return

        # Accept Twilio INVITEs to sip:t_test_CA...@domain (not only the Twilio DID).
        updated = await lk.sip.update_inbound_trunk(
            trunk_id,
            SIPInboundTrunkInfo(
                sip_trunk_id=trunk_id,
                name=trunk.name,
                numbers=["*"],
                allowed_addresses=TWILIO_SIG_IPS,
                allowed_numbers=[],
            ),
        )
        print(f"\nUpdated trunk numbers={list(updated.numbers)}")
        print(
            "\nPer-call dispatch rules are now created by voice-gateway on each /call/incoming."
        )
        print(f"Set LIVEKIT_SIP_TRUNK_ID={trunk_id} in .env.dev")
    finally:
        await lk.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trunk-id", help="LiveKit inbound trunk ID (default: first trunk)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(_run(args.trunk_id, args.dry_run))


if __name__ == "__main__":
    main()
