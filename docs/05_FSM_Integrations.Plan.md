# 05 — FSM Integrations Plan

**Service:** `dispatch-adapter`  
**Pattern:** Strategy Pattern (pluggable FSM backends)  
**Supported FSMs:** ServiceTitan · Housecall Pro  
**Status:** Planning  

---

## 1. Design: Strategy Pattern

Every home service business uses a different Field Service Management (FSM) platform. The dispatch adapter uses the **Strategy Pattern** — a single `DispatchAdapter` interface with swappable backends.

```python
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
```

---

## 2. ServiceTitan Adapter

### 2.1 Auth (OAuth 2.0 Client Credentials)

```python
# services/dispatch-adapter/adapters/service_titan.py

import httpx
from datetime import datetime, timedelta

class ServiceTitanAuth:
    TOKEN_URL = "https://auth.servicetitan.io/connect/token"

    def __init__(self, client_id: str, client_secret: str, tenant_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.st_tenant_id = tenant_id
        self._token: str | None = None
        self._expires_at: datetime | None = None

    async def get_token(self) -> str:
        if self._token and datetime.utcnow() < self._expires_at:
            return self._token

        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            })
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            self._expires_at = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 60)
            return self._token
```

### 2.2 Job Creation Flow (3 API calls)

```python
class ServiceTitanAdapter(DispatchAdapterBase):
    BASE_URL = "https://api.servicetitan.io/v2/tenant/{tenant_id}"

    async def create_job(self, payload: JobPayload) -> JobResult:
        token = await self.auth.get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "ST-App-Key": self.app_key,
            "Content-Type": "application/json",
        }
        base = self.BASE_URL.format(tenant_id=self.st_tenant_id)

        async with httpx.AsyncClient() as client:

            # Step 1: Find or create customer
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
                    }
                }
            )
            customer_id = customer_resp.json()["id"]

            # Step 2: Create booking/appointment
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
                    "duration": 120,   # 2h default, tech updates on-site
                    "externalData": {
                        "key": "ai_estimate",
                        "value": f"${payload.estimate_min:.0f}–${payload.estimate_max:.0f}"
                    }
                }
            )
            booking_id = booking_resp.json()["id"]

            # Step 3: Confirm and dispatch
            dispatch_resp = await client.post(
                f"{base}/jpm/bookings/{booking_id}/confirm",
                headers=headers,
            )

            # Fetch technician details
            tech_resp = await client.get(
                f"{base}/settings/technicians/{payload.tech_id}",
                headers=headers,
            )
            tech = tech_resp.json()

            return JobResult(
                job_id=str(booking_id),
                booking_confirmed=True,
                tech_name=f"{tech['name']}",
                tech_phone=tech.get("phoneNumber", ""),
                eta_window=payload.preferred_window,
                confirmation_number=f"ST-{booking_id}",
            )
```

### 2.3 Get Available Technicians

```python
    async def get_available_technicians(
        self, tenant_id, category, location, is_emergency
    ) -> list[dict]:
        token = await self.auth.get_token()
        base = self.BASE_URL.format(tenant_id=self.st_tenant_id)

        # ServiceTitan capacity API
        resp = await httpx.AsyncClient().get(
            f"{base}/dispatch/capacity",
            headers={"Authorization": f"Bearer {token}", "ST-App-Key": self.app_key},
            params={
                "startsOnOrAfter": datetime.utcnow().isoformat(),
                "endsOnOrBefore": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
                "businessUnitId": self.business_unit_id,
            }
        )
        slots = resp.json()["data"]

        # Filter by category + availability
        return [
            {
                "tech_id": slot["technicianId"],
                "name": slot["technicianName"],
                "available_at": slot["start"],
            }
            for slot in slots
            if slot["available"] and self._tech_matches_category(slot, category)
        ]
```

---

## 3. Housecall Pro Adapter

### 3.1 Auth (API Key, simpler)

```python
class HousecallProAdapter(DispatchAdapterBase):
    BASE_URL = "https://api.housecallpro.com/api"

    def __init__(self, api_key: str):
        self.headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        }
```

### 3.2 Job Creation (single call)

```python
    async def create_job(self, payload: JobPayload) -> JobResult:
        async with httpx.AsyncClient() as client:

            # HCP combines customer + job in one call
            resp = await client.post(
                f"{self.BASE_URL}/jobs",
                headers=self.headers,
                json={
                    "customer": {
                        "first_name": payload.caller_name.split()[0],
                        "last_name": " ".join(payload.caller_name.split()[1:]),
                        "mobile_number": payload.caller_phone,
                    },
                    "address": {
                        "street": payload.address,
                    },
                    "line_items": [
                        {
                            "name": payload.problem,
                            "description": f"AI Estimate: ${payload.estimate_min:.0f}–${payload.estimate_max:.0f}",
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
            )
            resp.raise_for_status()
            job = resp.json()

            return JobResult(
                job_id=job["id"],
                booking_confirmed=True,
                tech_name=job.get("assigned_employees", [{}])[0].get("name", ""),
                tech_phone="",
                eta_window=payload.preferred_window,
                confirmation_number=f"HCP-{job['id']}",
            )
```

---

## 4. Adapter Factory (Tenant Routing)

```python
# services/dispatch-adapter/factory.py

from .adapters.service_titan import ServiceTitanAdapter
from .adapters.housecall_pro import HousecallProAdapter
from shared.clients.vault import AzureKeyVaultClient

vault = AzureKeyVaultClient()

async def get_adapter(tenant_id: str) -> DispatchAdapterBase:
    config = await vault.get_tenant_config(tenant_id)

    if config["fsm"] == "servicetitan":
        return ServiceTitanAdapter(
            client_id=config["st_client_id"],
            client_secret=config["st_client_secret"],
            st_tenant_id=config["st_tenant_id"],
            app_key=config["st_app_key"],
            business_unit_id=config["st_business_unit_id"],
        )
    elif config["fsm"] == "housecall_pro":
        return HousecallProAdapter(api_key=config["hcp_api_key"])
    else:
        raise ValueError(f"Unknown FSM: {config['fsm']}")
```

---

## 5. Retry & Queue Strategy

FSM APIs can be slow or down. The dispatch adapter uses:
- 3 retries with exponential backoff on HTTP errors
- If all retries fail → publish job to **Azure Service Bus** queue
- A background worker polls the queue and retries with 30s intervals

```python
# services/dispatch-adapter/queue_handler.py

from azure.servicebus.aio import ServiceBusClient
import json

async def publish_failed_job(payload: JobPayload):
    async with ServiceBusClient.from_connection_string(SB_CONN_STR) as client:
        async with client.get_queue_sender("failed-dispatch") as sender:
            await sender.send_messages(
                ServiceBusMessage(payload.model_dump_json())
            )

async def retry_worker():
    """Background task: consumes failed-dispatch queue, retries"""
    async with ServiceBusClient.from_connection_string(SB_CONN_STR) as client:
        async with client.get_queue_receiver("failed-dispatch") as receiver:
            async for msg in receiver:
                payload = JobPayload(**json.loads(str(msg)))
                try:
                    adapter = await get_adapter(payload.tenant_id)
                    await adapter.create_job(payload)
                    await receiver.complete_message(msg)
                except Exception:
                    await receiver.abandon_message(msg)  # retry later
```

---

## 6. Notification Service (Post-Booking)

After a job is confirmed, fire-and-forget SMS:

```python
# services/notification-service/sms.py

from twilio.rest import Client

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
```

---

## 7. Tenant Config Schema (Azure Key Vault)

Each tenant's secrets stored as a single JSON blob in Key Vault:

```json
{
  "tenant_id": "t_abc123",
  "business_name": "Dallas Plumbing Co.",
  "fsm": "servicetitan",
  "st_client_id": "...",
  "st_client_secret": "...",
  "st_tenant_id": "...",
  "st_app_key": "...",
  "st_business_unit_id": "12345",
  "twilio_from_number": "+12145550001",
  "timezone": "America/Chicago",
  "service_categories": ["plumbing"],
  "emergency_surcharge_pct": 30
}
```

---

## Next: [06_Data_Layer.Plan.md](./06_Data_Layer.Plan.md)
