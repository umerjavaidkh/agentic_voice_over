from fastapi import FastAPI, HTTPException

from models import BookingConfirmationRequest
from sms import send_booking_confirmation

app = FastAPI(title="notification-service")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "notification-service"}


@app.post("/notify/booking-confirmed")
async def booking_confirmed(req: BookingConfirmationRequest):
    try:
        await send_booking_confirmation(
            to_phone=req.phone_number,
            tech_name=req.tech_name,
            eta_window=req.eta_window,
            address=req.address,
            estimate_range=req.estimate_range,
            confirmation_number=req.confirmation_number,
            business_name=req.business_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "sent", "to": req.phone_number}
