from pydantic import BaseModel


class BookingConfirmationRequest(BaseModel):
    phone_number: str
    tech_name: str
    eta_window: str
    address: str
    estimate_range: str
    confirmation_number: str
    business_name: str
