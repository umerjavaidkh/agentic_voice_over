# services/dispatch-adapter/adapters/service_titan.py

from datetime import datetime, timedelta

import httpx

from adapters.service_titan_auth import ServiceTitanAuth
from base import DispatchAdapterBase, JobPayload, JobResult

_CATEGORY_JOB_TYPES = {
    "plumbing": "jt-plumbing",
    "hvac": "jt-hvac",
    "roofing": "jt-roofing",
    "electrical": "jt-electrical",
    "general": "jt-general",
}

_WINDOW_OFFSETS = {
    "next_2_hours": timedelta(hours=2),
    "tomorrow_morning": timedelta(days=1),
}


class ServiceTitanAdapter(DispatchAdapterBase):
    BASE_URL = "https://api.servicetitan.io/v2/tenant/{tenant_id}"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        st_tenant_id: str,
        app_key: str,
        business_unit_id: str,
    ):
        self.st_tenant_id = st_tenant_id
        self.app_key = app_key
        self.business_unit_id = business_unit_id
        self.auth = ServiceTitanAuth(client_id, client_secret, st_tenant_id)

    def _parse_city(self, address: str) -> str:
        parts = [part.strip() for part in address.split(",")]
        return parts[-1] if len(parts) > 1 else ""

    def _category_to_job_type(self, category: str) -> str:
        return _CATEGORY_JOB_TYPES.get(category, _CATEGORY_JOB_TYPES["general"])

    def _parse_preferred_window(self, window: str) -> str:
        offset = _WINDOW_OFFSETS.get(window, timedelta(hours=4))
        return (datetime.utcnow() + offset).isoformat()

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "ST-App-Key": self.app_key,
            "Content-Type": "application/json",
        }

    async def _step_create_customer(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        base: str,
        payload: JobPayload,
    ) -> str:
        customer_resp = await client.post(
            f"{base}/crm/customers",
            headers=headers,
            json={
                "name": payload.caller_name,
                "type": "Residential",
                "contacts": [
                    {"type": "Phone", "value": payload.caller_phone},
                ],
                "address": {
                    "street": payload.address,
                    "city": self._parse_city(payload.address),
                },
            },
        )
        customer_resp.raise_for_status()
        return customer_resp.json()["id"]

    async def _step_create_booking(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        base: str,
        payload: JobPayload,
        customer_id: str,
    ) -> str:
        booking_resp = await client.post(
            f"{base}/jpm/bookings",
            headers=headers,
            json={
                "customerId": customer_id,
                "businessUnitId": self.business_unit_id,
                "jobTypeId": self._category_to_job_type(payload.service_category),
                "priority": "Urgent" if payload.urgency == "emergency" else "Normal",
                "summary": payload.problem,
                "preferredTechnician": {"id": payload.tech_id},
                "start": self._parse_preferred_window(payload.preferred_window),
                "duration": 120,
                "externalData": {
                    "key": "ai_estimate",
                    "value": f"${payload.estimate_min:.0f}–${payload.estimate_max:.0f}",
                },
            },
        )
        booking_resp.raise_for_status()
        return booking_resp.json()["id"]

    async def _step_confirm_dispatch(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        base: str,
        booking_id: str,
        tech_id: str,
    ) -> dict:
        dispatch_resp = await client.post(
            f"{base}/jpm/bookings/{booking_id}/confirm",
            headers=headers,
        )
        dispatch_resp.raise_for_status()

        tech_resp = await client.get(
            f"{base}/settings/technicians/{tech_id}",
            headers=headers,
        )
        tech_resp.raise_for_status()
        return tech_resp.json()

    async def create_job(self, payload: JobPayload) -> JobResult:
        token = await self.auth.get_token()
        headers = self._auth_headers(token)
        base = self.BASE_URL.format(tenant_id=self.st_tenant_id)

        async with httpx.AsyncClient() as client:
            customer_id = await self._step_create_customer(client, headers, base, payload)
            booking_id = await self._step_create_booking(
                client, headers, base, payload, customer_id
            )
            tech = await self._step_confirm_dispatch(
                client, headers, base, booking_id, payload.tech_id
            )

        return JobResult(
            job_id=str(booking_id),
            booking_confirmed=True,
            tech_name=f"{tech['name']}",
            tech_phone=tech.get("phoneNumber", ""),
            eta_window=payload.preferred_window,
            confirmation_number=f"ST-{booking_id}",
        )

    async def get_available_technicians(
        self,
        tenant_id: str,
        category: str,
        location: str,
        is_emergency: bool,
    ) -> list[dict]:
        raise NotImplementedError("ServiceTitanAdapter.get_available_technicians — section 2.3")

    async def health_check(self) -> bool:
        try:
            await self.auth.get_token()
            return True
        except Exception:
            return False
