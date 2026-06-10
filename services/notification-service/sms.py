# services/notification-service/sms.py

import os
import re

from twilio.rest import Client

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")

_E164_PHONE_RE = re.compile(r"^\+[1-9]\d{1,14}$")


def _validate_booking_confirmation_inputs(to_phone: str, tech_name: str) -> None:
    if not tech_name or not tech_name.strip():
        raise ValueError("tech_name is required")
    if not _E164_PHONE_RE.match(to_phone):
        raise ValueError(f"Invalid phone format: {to_phone}")


def _build_confirmation_body(
    *,
    business_name: str,
    tech_name: str,
    eta_window: str,
    address: str,
    estimate_range: str,
    confirmation_number: str,
) -> str:
    return (
        f"✅ {business_name}: Your appointment is confirmed!\n"
        f"Technician: {tech_name}\n"
        f"ETA: {eta_window}\n"
        f"Address: {address}\n"
        f"Estimate: {estimate_range}\n"
        f"Ref: {confirmation_number}"
    )


async def send_booking_confirmation(
    to_phone: str,
    tech_name: str,
    eta_window: str,
    address: str,
    estimate_range: str,
    confirmation_number: str,
    business_name: str,
):
    _validate_booking_confirmation_inputs(to_phone, tech_name)
    body = _build_confirmation_body(
        business_name=business_name,
        tech_name=tech_name,
        eta_window=eta_window,
        address=address,
        estimate_range=estimate_range,
        confirmation_number=confirmation_number,
    )
    client = Client(TWILIO_SID, TWILIO_TOKEN)
    client.messages.create(
        body=body,
        from_=TWILIO_FROM_NUMBER,
        to=to_phone,
    )
