import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from base import JobPayload
from queue_handler import FAILED_DISPATCH_QUEUE, publish_failed_job, retry_worker


def _sample_payload(**overrides) -> JobPayload:
    defaults = {
        "tenant_id": "t_abc123",
        "caller_name": "Ahmed Khan",
        "caller_phone": "+15551234567",
        "address": "123 Main Street, Dubai",
        "problem": "Water heater leaking",
        "service_category": "plumbing",
        "urgency": "emergency",
        "estimate_min": 800.0,
        "estimate_max": 1800.0,
        "tech_id": "tech-99",
        "preferred_window": "next_2_hours",
    }
    defaults.update(overrides)
    return JobPayload(**defaults)


def _async_cm(return_value):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=return_value)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


class _AsyncMessageIter:
    def __init__(self, messages):
        self._messages = list(messages)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._messages):
            raise StopAsyncIteration
        message = self._messages[self._index]
        self._index += 1
        return message


class _MockReceiver:
    def __init__(self, messages):
        self._messages = messages
        self.complete_message = AsyncMock()
        self.abandon_message = AsyncMock()

    def __aiter__(self):
        return _AsyncMessageIter(self._messages)


@pytest.mark.asyncio
async def test_publish_failed_job_sends_payload_to_queue():
    payload = _sample_payload()
    mock_sender = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_queue_sender = MagicMock(return_value=_async_cm(mock_sender))

    with patch("queue_handler.ServiceBusClient") as mock_sb_client, patch(
        "queue_handler.SB_CONN_STR", "Endpoint=sb://test.servicebus.windows.net/;..."
    ):
        mock_sb_client.from_connection_string.return_value = _async_cm(mock_client)
        await publish_failed_job(payload)

    mock_sb_client.from_connection_string.assert_called_once_with(
        "Endpoint=sb://test.servicebus.windows.net/;..."
    )
    mock_client.get_queue_sender.assert_called_once_with(FAILED_DISPATCH_QUEUE)
    mock_sender.send_messages.assert_awaited_once()

    sent_message = mock_sender.send_messages.await_args.args[0]
    assert json.loads(str(sent_message)) == payload.model_dump()


@pytest.mark.asyncio
async def test_retry_worker_completes_message_on_success():
    payload = _sample_payload()
    mock_msg = MagicMock()
    mock_msg.__str__ = MagicMock(return_value=payload.model_dump_json())

    mock_receiver = _MockReceiver([mock_msg])

    mock_client = MagicMock()
    mock_client.get_queue_receiver = MagicMock(return_value=_async_cm(mock_receiver))

    mock_adapter = AsyncMock()
    mock_adapter.create_job = AsyncMock()

    with patch("queue_handler.ServiceBusClient") as mock_sb_client, patch(
        "queue_handler.get_adapter", AsyncMock(return_value=mock_adapter)
    ):
        mock_sb_client.from_connection_string.return_value = _async_cm(mock_client)
        await retry_worker()

    mock_adapter.create_job.assert_awaited_once_with(payload)
    mock_receiver.complete_message.assert_awaited_once_with(mock_msg)
    mock_receiver.abandon_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_worker_abandons_message_on_failure():
    payload = _sample_payload()
    mock_msg = MagicMock()
    mock_msg.__str__ = MagicMock(return_value=payload.model_dump_json())

    mock_receiver = _MockReceiver([mock_msg])

    mock_client = MagicMock()
    mock_client.get_queue_receiver = MagicMock(return_value=_async_cm(mock_receiver))

    mock_adapter = AsyncMock()
    mock_adapter.create_job = AsyncMock(side_effect=RuntimeError("FSM unavailable"))

    with patch("queue_handler.ServiceBusClient") as mock_sb_client, patch(
        "queue_handler.get_adapter", AsyncMock(return_value=mock_adapter)
    ):
        mock_sb_client.from_connection_string.return_value = _async_cm(mock_client)
        await retry_worker()

    mock_receiver.abandon_message.assert_awaited_once_with(mock_msg)
    mock_receiver.complete_message.assert_not_awaited()
