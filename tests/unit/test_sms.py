from unittest.mock import MagicMock, patch

import pytest

from sms import send_booking_confirmation


@pytest.mark.asyncio
async def test_send_booking_confirmation_body_contains_required_fields():
    mock_client = MagicMock()

    with patch("sms.Client", return_value=mock_client), patch(
        "sms.TWILIO_SID", "AC-test-sid"
    ), patch("sms.TWILIO_TOKEN", "test-token"), patch(
        "sms.TWILIO_FROM_NUMBER", "+12145550001"
    ):
        await send_booking_confirmation(
            to_phone="+15551234567",
            tech_name="Mike Torres",
            eta_window="next_2_hours",
            address="123 Main Street, Dubai",
            estimate_range="$800–$1800",
            confirmation_number="ST-42",
            business_name="Dallas Plumbing Co.",
        )

    mock_client.messages.create.assert_called_once_with(
        body=(
            "✅ Dallas Plumbing Co.: Your appointment is confirmed!\n"
            "Technician: Mike Torres\n"
            "ETA: next_2_hours\n"
            "Address: 123 Main Street, Dubai\n"
            "Estimate: $800–$1800\n"
            "Ref: ST-42"
        ),
        from_="+12145550001",
        to="+15551234567",
    )

    body = mock_client.messages.create.call_args.kwargs["body"]
    assert "Mike Torres" in body
    assert "next_2_hours" in body
    assert "ST-42" in body
