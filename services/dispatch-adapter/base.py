# services/dispatch-adapter/base.py

from abc import ABC, abstractmethod

from pydantic import BaseModel


class JobPayload(BaseModel):
    tenant_id: str
    caller_name: str
    caller_phone: str
    address: str
    problem: str
    service_category: str
    urgency: str
    estimate_min: float
    estimate_max: float
    tech_id: str
    preferred_window: str       # "next_2_hours" | "tomorrow_morning" | etc.
    notes: str = ""


class JobResult(BaseModel):
    job_id: str
    booking_confirmed: bool
    tech_name: str
    tech_phone: str
    eta_window: str
    confirmation_number: str


class DispatchAdapterBase(ABC):
    @abstractmethod
    async def create_job(self, payload: JobPayload) -> JobResult:
        ...

    @abstractmethod
    async def get_available_technicians(
        self,
        tenant_id: str,
        category: str,
        location: str,
        is_emergency: bool,
    ) -> list[dict]:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...
