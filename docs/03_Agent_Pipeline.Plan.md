# 03 — Agent Pipeline Plan

**Service:** `agent-brain`  
**Framework:** LangGraph (StateGraph)  
**LLM:** GPT-4o-mini (primary) / Claude Haiku (fallback)  
**Status:** Planning  

---

## 1. Graph Overview

```
                    ┌─────────┐
                    │  START  │
                    └────┬────┘
                         │ raw transcript
                         ▼
                  ┌─────────────┐
                  │ IntentNode  │  ← "what is the problem?"
                  └──────┬──────┘
                         │ intent + urgency signal
                         ▼
                  ┌─────────────────┐
                  │  EntityNode     │  ← "collect address, appliance, age"
                  └────────┬────────┘
                           │ entities confirmed
               ┌───────────┴────────────┐
               ▼                        ▼
        ┌─────────────┐        ┌──────────────────┐
        │ PricingTool │        │ GeoRoutingTool   │
        └──────┬──────┘        └────────┬─────────┘
               └──────────┬────────────┘
                           ▼
                  ┌─────────────────┐
                  │  QualifierNode  │  ← triage: emergency vs scheduled
                  └────────┬────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
       [urgency=HIGH]            [urgency=NORMAL]
       Emergency branch          Scheduled branch
              └──────────┬────────────┘
                          ▼
                 ┌─────────────────┐
                 │ DispatcherNode  │  ← book job in FSM
                 └────────┬────────┘
                           │
                    ┌──────┴──────┐
                    ▼             ▼
             [success]       [failure]
                 │                │
              confirm         fallback
                 └──────┬──────┘
                        ▼
                    ┌───────┐
                    │  END  │
                    └───────┘
```

---

## 2. Shared State Schema

This is the single source of truth across all nodes. Built with Pydantic.

```python
# shared/models/agent_state.py

from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

class UrgencyLevel(str, Enum):
    EMERGENCY = "emergency"     # same-day, within hours
    URGENT    = "urgent"        # within 24 hours
    NORMAL    = "normal"        # scheduled appointment

class ServiceCategory(str, Enum):
    PLUMBING  = "plumbing"
    HVAC      = "hvac"
    ROOFING   = "roofing"
    ELECTRICAL= "electrical"
    GENERAL   = "general"

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
    appliance_type: Optional[str] = None          # "water heater", "AC unit"
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
    pricing_confidence: float = 0.0              # 0.0–1.0

    # Dispatch
    assigned_technician: Optional[Technician] = None
    job_id: Optional[str] = None                 # FSM job ID
    booking_confirmed: bool = False
    dispatch_eta: Optional[str] = None           # "within 2 hours"

    # Fallback
    fallback_triggered: bool = False
    human_handoff_required: bool = False
    error_message: Optional[str] = None

    # Agent response to speak
    agent_response: Optional[str] = None
```

---

## 3. Node Implementations

### 3.1 IntentNode

**Purpose:** Classify the caller's problem. Extract urgency signal from language.

```python
# services/agent-brain/nodes/intent_node.py

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import json

INTENT_SYSTEM_PROMPT = """
You are an expert at understanding home service problems from brief phone descriptions.

Extract from the caller's message:
1. problem_description: one clear sentence describing the issue
2. service_category: one of [plumbing, hvac, roofing, electrical, general]
3. appliance_type: specific appliance if mentioned (e.g. "water heater", "AC unit", "furnace")
4. urgency_signal: one of [emergency, urgent, normal]
   - emergency: active leak, no heat in winter, safety risk, "right now", "badly", "flooding"
   - urgent: not working, broken, "as soon as possible"
   - normal: maintenance, intermittent issue, "when you have time"

Return ONLY valid JSON. No explanation.
"""

async def intent_node(state: AgentState) -> AgentState:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    last_message = state.conversation_history[-1]["content"]

    response = await llm.ainvoke([
        SystemMessage(content=INTENT_SYSTEM_PROMPT),
        HumanMessage(content=last_message),
    ])

    data = json.loads(response.content)
    state.problem_description = data["problem_description"]
    state.service_category = ServiceCategory(data["service_category"])
    state.appliance_type = data.get("appliance_type")
    state.urgency_level = UrgencyLevel(data["urgency_signal"])
    state.is_emergency = state.urgency_level == UrgencyLevel.EMERGENCY

    # Ask for address next
    state.agent_response = "Got it. What's the address where you need the service?"
    return state
```

---

### 3.2 EntityNode

**Purpose:** Collect all required entities through conversational turns. Multi-turn aware.

```python
# services/agent-brain/nodes/entity_node.py

ENTITY_SYSTEM_PROMPT = """
You are collecting information needed to dispatch a home service technician.

Already collected: {collected}
Still needed: {missing}

Current caller message: "{message}"

Extract any new information. If address is provided, normalize it to: 
"[house number] [street], [city]"

Return JSON with only the fields you found in THIS message.
If you found everything needed, set "entities_complete": true.
"""

REQUIRED_ENTITIES = ["address", "caller_name"]
OPTIONAL_ENTITIES = ["appliance_age_years"]

async def entity_node(state: AgentState) -> AgentState:
    collected = {}
    if state.address: collected["address"] = state.address
    if state.caller_name: collected["caller_name"] = state.caller_name

    missing = [e for e in REQUIRED_ENTITIES if e not in collected]

    if not missing:
        # All entities collected, proceed to qualification
        return state

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    last_message = state.conversation_history[-1]["content"]

    response = await llm.ainvoke([
        SystemMessage(content=ENTITY_SYSTEM_PROMPT.format(
            collected=collected,
            missing=missing,
            message=last_message
        ))
    ])

    data = json.loads(response.content)
    if "address" in data: state.address = data["address"]
    if "caller_name" in data: state.caller_name = data["caller_name"]

    # If still missing something, ask for it
    still_missing = [e for e in REQUIRED_ENTITIES
                     if not getattr(state, e)]
    if still_missing:
        prompts = {
            "address": "What's the address for the service?",
            "caller_name": "And what's your name?",
        }
        state.agent_response = prompts[still_missing[0]]
    
    return state
```

---

### 3.3 QualifierNode

**Purpose:** Final triage. Confirm urgency with caller. Present estimate. Get verbal confirmation.

```python
# services/agent-brain/nodes/qualifier_node.py

async def qualifier_node(state: AgentState) -> AgentState:
    # By this point, pricing and geo tools have populated state
    tech = state.assigned_technician
    
    if state.is_emergency:
        state.agent_response = (
            f"That sounds urgent. I can have {tech.name} at "
            f"{state.address} within {tech.eta_minutes} minutes. "
            f"The estimate is ${state.estimate_min:.0f}–${state.estimate_max:.0f}. "
            f"Shall I confirm that booking?"
        )
    else:
        state.agent_response = (
            f"I can schedule a technician to come out. "
            f"We have availability tomorrow between 9 AM and 12 PM. "
            f"The estimate is ${state.estimate_min:.0f}–${state.estimate_max:.0f}. "
            f"Does that work for you?"
        )
    
    return state

def should_dispatch(state: AgentState) -> str:
    """Conditional edge: did caller confirm?"""
    last = state.conversation_history[-1]["content"].lower()
    confirm_words = ["yes", "yeah", "sure", "go ahead", "book it", "ok", "confirm"]
    deny_words = ["no", "cancel", "wait", "hold on", "not yet"]
    
    if any(w in last for w in confirm_words):
        return "dispatch"
    elif any(w in last for w in deny_words):
        return "clarify"
    else:
        return "re_ask"  # Agent asks again
```

---

### 3.4 DispatcherNode

**Purpose:** Create the job in FSM. Return confirmation details.

```python
# services/agent-brain/nodes/dispatcher_node.py

from shared.clients.dispatch_client import DispatchClient

async def dispatcher_node(state: AgentState) -> AgentState:
    client = DispatchClient(tenant_id=state.tenant_id)
    
    try:
        job_result = await client.create_job({
            "caller_name": state.caller_name,
            "caller_phone": state.caller_phone,
            "address": state.address,
            "problem": state.problem_description,
            "service_category": state.service_category,
            "urgency": state.urgency_level,
            "estimate_min": state.estimate_min,
            "estimate_max": state.estimate_max,
            "tech_id": state.assigned_technician.tech_id,
        })
        
        state.job_id = job_result["job_id"]
        state.booking_confirmed = True
        state.agent_response = (
            f"You're all set, {state.caller_name}. "
            f"{state.assigned_technician.name} will be there "
            f"{state.dispatch_eta}. "
            f"I'm sending a text confirmation to {state.caller_phone} now. "
            f"Is there anything else I can help with?"
        )
    except Exception as e:
        state.fallback_triggered = True
        state.error_message = str(e)
        state.agent_response = (
            "I'm having trouble completing the booking on my end. "
            "Let me take your details and have our team call you right back."
        )
    
    return state
```

---

## 4. LangGraph Graph Assembly

```python
# services/agent-brain/graph.py

from langgraph.graph import StateGraph, END
from .nodes import intent_node, entity_node, qualifier_node, dispatcher_node
from .tools import run_pricing_tool, run_geo_tool

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("intent", intent_node)
    graph.add_node("entity", entity_node)
    graph.add_node("pricing", run_pricing_tool)
    graph.add_node("geo_routing", run_geo_tool)
    graph.add_node("qualifier", qualifier_node)
    graph.add_node("dispatcher", dispatcher_node)

    # Edges
    graph.set_entry_point("intent")
    graph.add_edge("intent", "entity")

    # After entity: run pricing + geo in parallel
    graph.add_edge("entity", "pricing")
    graph.add_edge("entity", "geo_routing")
    graph.add_edge("pricing", "qualifier")
    graph.add_edge("geo_routing", "qualifier")

    # Qualifier conditional
    graph.add_conditional_edges(
        "qualifier",
        should_dispatch,
        {
            "dispatch": "dispatcher",
            "clarify": "qualifier",   # loop back
            "re_ask": "qualifier",
        }
    )

    graph.add_edge("dispatcher", END)
    return graph.compile()
```

---

## 5. Multi-Turn Conversation Loop

The graph is invoked once per caller utterance. State is persisted in Redis between turns.

```python
# services/agent-brain/session_runner.py

import redis.asyncio as aioredis
import json

class SessionRunner:
    def __init__(self, redis_client, graph):
        self.redis = redis_client
        self.graph = graph

    async def process_turn(self, call_sid: str, user_text: str) -> str:
        # Load state from Redis
        state_raw = await self.redis.get(f"call:{call_sid}")
        state = AgentState(**json.loads(state_raw)) if state_raw else AgentState(call_sid=call_sid)

        # Append new user turn
        state.conversation_history.append({"role": "user", "content": user_text})
        state.turn_count += 1

        # Run graph
        result_state = await self.graph.ainvoke(state)

        # Persist updated state
        await self.redis.setex(
            f"call:{call_sid}",
            1800,  # 30 min TTL
            result_state.model_dump_json()
        )

        return result_state.agent_response
```

---

## 6. Tool Definitions

### PricingTool

```python
# services/agent-brain/tools/pricing_tool.py

async def run_pricing_tool(state: AgentState) -> AgentState:
    from pricing_service.client import PricingClient
    
    if not state.problem_description:
        return state
    
    result = await PricingClient().lookup(
        description=state.problem_description,
        category=state.service_category,
        tenant_id=state.tenant_id,
    )
    
    state.estimate_min = result.min_price
    state.estimate_max = result.max_price
    state.pricing_confidence = result.confidence
    return state
```

### GeoRoutingTool

```python
# services/agent-brain/tools/geo_tool.py

async def run_geo_tool(state: AgentState) -> AgentState:
    from shared.utils.geo import find_nearest_technician
    
    if not state.address:
        return state
    
    tech = await find_nearest_technician(
        address=state.address,
        category=state.service_category,
        tenant_id=state.tenant_id,
        is_emergency=state.is_emergency,
    )
    
    state.assigned_technician = tech
    state.dispatch_eta = (
        f"within {tech.eta_minutes} minutes"
        if state.is_emergency
        else "during your scheduled window"
    )
    return state
```

---

## 7. LangSmith Tracing Config

```python
# services/agent-brain/config.py

import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "voice-agent-home-services"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
```

Every graph invocation produces a LangSmith trace with:
- Node timing (which node took longest)
- Token usage per LLM call
- Tool call inputs/outputs
- Final state delta

---

## Next: [04_Pricing_Engine.Plan.md](./04_Pricing_Engine.Plan.md)
