class DispatchClient:
    """HTTP client for the dispatch-adapter service (ServiceTitan / HCP)."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    async def create_job(self, payload: dict) -> dict:
        from base import JobPayload
        from factory import get_adapter

        service_category = payload["service_category"]
        if hasattr(service_category, "value"):
            service_category = service_category.value

        urgency = payload["urgency"]
        if hasattr(urgency, "value"):
            urgency = urgency.value

        job_payload = JobPayload(
            tenant_id=self.tenant_id,
            caller_name=payload.get("caller_name") or "Customer",
            caller_phone=payload["caller_phone"],
            address=payload.get("address") or "",
            problem=payload.get("problem") or "",
            service_category=str(service_category),
            urgency=str(urgency),
            estimate_min=float(payload["estimate_min"]),
            estimate_max=float(payload["estimate_max"]),
            tech_id=payload["tech_id"],
            preferred_window=payload.get("preferred_window", "next_2_hours"),
            notes=payload.get("notes", ""),
        )

        adapter = await get_adapter(self.tenant_id)
        result = await adapter.create_job(job_payload)
        return {
            "job_id": result.job_id,
            "booking_confirmed": result.booking_confirmed,
            "confirmation_number": result.confirmation_number,
            "business_name": payload.get("business_name", "Home Services"),
        }
