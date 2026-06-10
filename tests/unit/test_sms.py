from unittest.mock import MagicMock, patch

import pytest

from sms import send_booking_confirmation


CONFIRMATION_KWARGS = {
    "to_phone": "+15551234567",
    "tech_name": "Mike Torres",
    "eta_window": "next_2_hours",
    "address": "123 Main Street, Dubai",
    "estimate_range": "$800–$1800",
    "confirmation_number": "ST-42",
    "business_name": "Dallas Plumbing Co.",
}


@pytest.mark.asyncio
async def test_send_booking_confirmation_happy_path():
    mock_client = MagicMock()

    with patch("sms.Client", return_value=mock_client) as mock_client_cls, patch(
        "sms.TWILIO_SID", "AC-test-sid"
    ), patch("sms.TWILIO_TOKEN", "test-token"), patch(
        "sms.TWILIO_FROM_NUMBER", "+12145550001"
    ):
        await send_booking_confirmation(**CONFIRMATION_KWARGS)

    mock_client_cls.assert_called_once_with("AC-test-sid", "test-token")
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


@pytest.mark.asyncio
async def test_send_booking_confirmation_missing_tech_name_raises_before_twilio():
    mock_client = MagicMock()

    with patch("sms.Client", return_value=mock_client):
        with pytest.raises(ValueError, match="tech_name is required"):
            await send_booking_confirmation(**{**CONFIRMATION_KWARGS, "tech_name": "   "})

    mock_client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_send_booking_confirmation_invalid_phone_raises_before_twilio():
    mock_client = MagicMock()

    with patch("sms.Client", return_value=mock_client):
        with pytest.raises(ValueError, match="Invalid phone format"):
            await send_booking_confirmation(**{**CONFIRMATION_KWARGS, "to_phone": "555-123-4567"})

    mock_client.messages.create.assert_not_called()
