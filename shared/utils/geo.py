from shared.models.agent_state import ServiceCategory, Technician


async def find_nearest_technician(
    *,
    address: str,
    category: ServiceCategory | None,
    tenant_id: str,
    is_emergency: bool,
) -> Technician:
    raise NotImplementedError("find_nearest_technician is implemented via geo-routing service")
