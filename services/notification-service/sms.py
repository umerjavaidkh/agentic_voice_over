# services/notification-service/sms.py

import os

from twilio.rest import Client

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")


async def send_booking_confirmation(
    to_phone: str,
    tech_name: str,
    eta_window: str,
    address: str,
    estimate_range: str,
    confirmation_number: str,
    business_name: str,
):
    body = (
        f"✅ {business_name}: Your appointment is confirmed!\n"
        f"Technician: {tech_name}\n"
        f"ETA: {eta_window}\n"
        f"Address: {address}\n"
        f"Estimate: {estimate_range}\n"
        f"Ref: {confirmation_number}"
    )
    client = Client(TWILIO_SID, TWILIO_TOKEN)
    client.messages.create(
        body=body,
        from_=TWILIO_FROM_NUMBER,
        to=to_phone,
    )
