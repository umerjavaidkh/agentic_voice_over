# services/dispatch-adapter/adapters/housecall_pro.py

from datetime import datetime, timedelta

import httpx

from base import DispatchAdapterBase, JobPayload, JobResult

_WINDOW_OFFSETS = {
    "next_2_hours": timedelta(hours=2),
    "tomorrow_morning": timedelta(days=1),
}

_WINDOW_DURATIONS = {
    "next_2_hours": timedelta(hours=2),
    "tomorrow_morning": timedelta(hours=4),
}


class HousecallProAdapter(DispatchAdapterBase):
    BASE_URL = "https://api.housecallpro.com/api"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        }

    def _parse_window(self, window: str) -> str:
        offset = _WINDOW_OFFSETS.get(window, timedelta(hours=4))
        return (datetime.utcnow() + offset).isoformat()

    def _parse_window_end(self, window: str) -> str:
        start_offset = _WINDOW_OFFSETS.get(window, timedelta(hours=4))
        duration = _WINDOW_DURATIONS.get(window, timedelta(hours=2))
        return (datetime.utcnow() + start_offset + duration).isoformat()

    def _build_job_request(self, payload: JobPayload) -> dict:
        name_parts = payload.caller_name.split()
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:])

        return {
            "customer": {
                "first_name": first_name,
                "last_name": last_name,
                "mobile_number": payload.caller_phone,
            },
            "address": {
                "street": payload.address,
            },
            "line_items": [
                {
                    "name": payload.problem,
                    "description": (
                        f"AI Estimate: ${payload.estimate_min:.0f}–${payload.estimate_max:.0f}"
                    ),
                    "unit_price": payload.estimate_min,
                    "quantity": 1,
                }
            ],
            "assigned_employee_ids": [payload.tech_id],
            "scheduled_start": self._parse_window(payload.preferred_window),
            "scheduled_end": self._parse_window_end(payload.preferred_window),
            "tags": [payload.urgency, "ai_booked"],
            "private_notes": f"Booked via AI voice agent. {payload.notes}",
        }

    async def create_job(self, payload: JobPayload) -> JobResult:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/jobs",
                headers=self.headers,
                json=self._build_job_request(payload),
            )
            resp.raise_for_status()
            job = resp.json()

        assigned_employees = job.get("assigned_employees") or []
        tech_name = assigned_employees[0].get("name", "") if assigned_employees else ""

        return JobResult(
            job_id=job["id"],
            booking_confirmed=True,
            tech_name=tech_name,
            tech_phone="",
            eta_window=payload.preferred_window,
            confirmation_number=f"HCP-{job['id']}",
        )

    async def get_available_technicians(
        self,
        tenant_id: str,
        category: str,
        location: str,
        is_emergency: bool,
    ) -> list[dict]:
        raise NotImplementedError("HousecallProAdapter.get_available_technicians is not in plan section 3")

    async def health_check(self) -> bool:
        return bool(self.api_key)
