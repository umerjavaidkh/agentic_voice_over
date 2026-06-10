# shared/models/agent_state.py

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class UrgencyLevel(str, Enum):
    EMERGENCY = "emergency"  # same-day, within hours
    URGENT = "urgent"  # within 24 hours
    NORMAL = "normal"  # scheduled appointment


class ServiceCategory(str, Enum):
    PLUMBING = "plumbing"
    HVAC = "hvac"
    ROOFING = "roofing"
    ELECTRICAL = "electrical"
    GENERAL = "general"


class Technician(BaseModel):
    tech_id: str
    name: str
    phone: str
    distance_km: float
    eta_minutes: int
    specialty: ServiceCategory


class AgentState(BaseModel):
    # Call metadata
    call_sid: str
    tenant_id: str
    caller_phone: str
    conversation_history: List[dict] = []  # [{role, content}]
    turn_count: int = 0

    # Extracted entities
    problem_description: Optional[str] = None
    service_category: Optional[ServiceCategory] = None
    appliance_type: Optional[str] = None  # "water heater", "AC unit"
    appliance_age_years: Optional[int] = None
    address: Optional[str] = None
    caller_name: Optional[str] = None

    # Triage + qualification
    urgency_level: Optional[UrgencyLevel] = None
    is_emergency: bool = False
    caller_confirmed: bool = False

    # Pricing
    estimate_min: Optional[float] = None
    estimate_max: Optional[float] = None
    pricing_confidence: float = 0.0  # 0.0–1.0

    # Dispatch
    assigned_technician: Optional[Technician] = None
    job_id: Optional[str] = None  # FSM job ID
    booking_confirmed: bool = False
    dispatch_eta: Optional[str] = None  # "within 2 hours"

    # Fallback
    fallback_triggered: bool = False
    human_handoff_required: bool = False
    error_message: Optional[str] = None

    # Agent response to speak
    agent_response: Optional[str] = None
