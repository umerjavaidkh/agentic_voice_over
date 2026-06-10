# services/dispatch-adapter/queue_handler.py

import json
import os

from azure.servicebus import ServiceBusMessage
from azure.servicebus.aio import ServiceBusClient

from base import JobPayload
from factory import get_adapter

FAILED_DISPATCH_QUEUE = "failed-dispatch"
SB_CONN_STR = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "")


async def publish_failed_job(payload: JobPayload) -> None:
    async with ServiceBusClient.from_connection_string(SB_CONN_STR) as client:
        async with client.get_queue_sender(FAILED_DISPATCH_QUEUE) as sender:
            await sender.send_messages(
                ServiceBusMessage(payload.model_dump_json())
            )


async def retry_worker() -> None:
    """Background task: consumes failed-dispatch queue, retries."""
    async with ServiceBusClient.from_connection_string(SB_CONN_STR) as client:
        async with client.get_queue_receiver(FAILED_DISPATCH_QUEUE) as receiver:
            async for msg in receiver:
                payload = JobPayload(**json.loads(str(msg)))
                try:
                    adapter = await get_adapter(payload.tenant_id)
                    await adapter.create_job(payload)
                    await receiver.complete_message(msg)
                except Exception:
                    await receiver.abandon_message(msg)
