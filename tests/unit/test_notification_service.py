import importlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


BOOKING_REQUEST = {
    "phone_number": "+15551234567",
    "tech_name": "Mike Torres",
    "eta_window": "next_2_hours",
    "address": "123 Main Street, Dubai",
    "estimate_range": "$800–$1800",
    "confirmation_number": "ST-42",
    "business_name": "Dallas Plumbing Co.",
}


@pytest.fixture
def notification_client():
    import main

    importlib.reload(main)
    with TestClient(main.app) as client:
        yield client


def test_booking_confirmed_happy_path(notification_client):
    mock_twilio_client = MagicMock()

    with patch("sms.Client", return_value=mock_twilio_client), patch(
        "sms.TWILIO_SID", "AC-test-sid"
    ), patch("sms.TWILIO_TOKEN", "test-token"), patch(
        "sms.TWILIO_FROM_NUMBER", "+12145550001"
    ):
        response = notification_client.post("/notify/booking-confirmed", json=BOOKING_REQUEST)

    assert response.status_code == 200
    assert response.json() == {"status": "sent", "to": "+15551234567"}
    mock_twilio_client.messages.create.assert_called_once()


def test_booking_confirmed_missing_tech_name_returns_400(notification_client):
    with patch("sms.Client") as mock_client_cls:
        response = notification_client.post(
            "/notify/booking-confirmed",
            json={**BOOKING_REQUEST, "tech_name": "   "},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "tech_name is required"
    mock_client_cls.assert_not_called()


def test_booking_confirmed_invalid_phone_returns_400(notification_client):
    with patch("sms.Client") as mock_client_cls:
        response = notification_client.post(
            "/notify/booking-confirmed",
            json={**BOOKING_REQUEST, "phone_number": "555-123-4567"},
        )

    assert response.status_code == 400
    assert "Invalid phone format" in response.json()["detail"]
    mock_client_cls.assert_not_called()


def test_health_endpoint(notification_client):
    response = notification_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "notification-service"}
