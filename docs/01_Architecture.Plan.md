# 01 — System Architecture Plan

**Project:** Home Services Voice Agent  
**Layer:** Full-stack overview  
**Status:** Planning  

---

## 1. Architectural Philosophy

This system is built on three principles:

- **Stream everything** — no blocking calls anywhere in the audio path
- **Fail gracefully** — if the AI can't book, it falls back to SMS lead capture, never dead air
- **Stateless services, stateful session** — each microservice is stateless; Redis holds all per-call state

---

## 2. System Layers

### Layer 0 — Telephony Ingress

```
Homeowner phone ──► Twilio SIP Trunk ──► Voice Gateway Service
                         │
                    (SIP/RTP media)
```

- Twilio receives the PSTN call
- Routes audio as RTP to a LiveKit room via SIP INVITE
- Voice Gateway Service manages the room lifecycle
- One LiveKit room = one call session

**Key config:**
- Twilio Programmable Voice webhook → `/call/incoming` on Voice Gateway
- LiveKit room created on webhook, SIP participant added
- LiveKit egress captures audio for recording

---

### Layer 1 — Voice Processing

```
Caller audio (PCM 16kHz) ──► Deepgram WebSocket ──► Transcript chunks
                                                           │
                                                    Agent Brain input
                                                           │
                                            Agent response text ──► ElevenLabs ──► Audio back to caller
```

- Deepgram streams `interim_results` for barge-in detection
- `is_final=true` chunks trigger LangGraph turn
- ElevenLabs streams MP3 chunks → LiveKit plays to caller
- Barge-in: if Deepgram detects speech during TTS, cancel current TTS stream immediately

---

### Layer 2 — Agent Brain

```
Transcript
    │
    ▼
┌──────────────────────────────────────────────────────┐
│                  LangGraph Graph                      │
│                                                       │
│  [START] ──► IntentNode ──► EntityNode               │
│                                  │                    │
│                          ┌───────┴────────┐           │
│                          ▼                ▼           │
│                    PricingTool      GeoRoutingTool    │
│                          │                │           │
│                          └───────┬────────┘           │
│                                  ▼                    │
│                           QualifierNode               │
│                                  │                    │
│                  ┌───────────────┴──────────────┐     │
│                  ▼                              ▼     │
│           [Emergency]                    [Scheduled]  │
│                  │                              │     │
│                  └──────────► DispatcherNode ◄──┘     │
│                                      │                │
│                                   [END]               │
└──────────────────────────────────────────────────────┘
```

- Each node is a Python function receiving/returning `AgentState`
- Conditional edges route on `urgency_level` enum
- All tool calls (pricing, geo) happen inside node functions
- LangSmith traces every edge transition

---

### Layer 3 — Intelligence Services

| Service | Input | Output |
|---------|-------|--------|
| Pricing Engine | Problem description embedding | `{min_price, max_price, service_category}` |
| Geo-routing | Caller address + technician locations | Ranked list of available techs |
| LLM (GPT-4o-mini) | Prompt + tool schemas | Structured JSON response |

These are internal FastAPI microservices — not called directly by the agent nodes via HTTP, but imported as Python modules in the agent brain service (same pod, no network hop for pricing).

---

### Layer 4 — Data Stores

| Store | Purpose | Access Pattern |
|-------|---------|----------------|
| Redis | Per-call session state | Write on every turn, read at turn start |
| Postgres + pgvector | Jobs, leads, price catalog | Write on booking, read for pricing lookup |
| Azure Blob Storage | Call recordings, transcripts, agent event logs | Write once, read for analytics/compliance |
| Azure Service Bus | Async dispatch queue | Publish after booking, FSM adapter consumes |

---

### Layer 5 — FSM Integrations

```
Dispatcher Node
      │
      ▼
DispatchAdapter (Strategy Pattern)
      │
      ├── ServiceTitanAdapter ──► ServiceTitan REST API
      └── HousecallProAdapter ──► Housecall Pro REST API

Post-booking:
      ├── NotificationService ──► Twilio SMS (homeowner)
      └── NotificationService ──► Email (business owner summary)
```

Each tenant (home service business) is configured with:
- Which FSM they use (ST or HCP)
- API credentials (stored in Azure Key Vault)
- Custom pricing catalog (their pgvector partition)

---

## 3. Data Flow — Happy Path

```
1.  Homeowner calls the business number
2.  Twilio routes to LiveKit room (Voice Gateway)
3.  Deepgram begins streaming STT
4.  Greeting plays: "Hi, you've reached [Business]. How can I help?"
5.  Caller: "My water heater is leaking really badly"
6.  Deepgram emits final transcript
7.  IntentNode → extracts: problem="water heater leak", urgency=HIGH
8.  EntityNode → asks: "What's your address?"
9.  Caller: "123 Main Street, Dubai"
10. EntityNode → extracts address, runs geo-lookup
11. PricingTool → embeds "water heater leaking" → returns $200–$450
12. QualifierNode → routes to Emergency branch
13. Agent: "I can have a plumber at your address within 2 hours. The estimate is $200–$450."
14. Caller confirms
15. DispatcherNode → ServiceTitan API: create job, assign nearest tech
16. NotificationService → SMS to homeowner with tech name + ETA
17. Call ends gracefully
18. Recording uploaded to Azure Blob Storage
19. Lead record written to Postgres
```

---

## 4. Failure Modes & Fallbacks

| Failure | Fallback |
|---------|---------|
| STT timeout | Prompt caller to repeat; max 2 retries, then transfer to on-call human |
| LLM API error | Pre-scripted response: "I'm having trouble. Let me take your number and call back." |
| FSM API down | Write job to Service Bus queue; adapter retries with exponential backoff |
| Geo-routing fails | Use pre-configured fallback technician per region |
| Pricing DB unreachable | Return hardcoded category-level ranges (wider bands) |
| Call drops mid-conversation | State persisted in Redis; can resume if caller calls back within 30min |

---

## 5. Multi-Tenancy Model

- Each business = one `tenant_id`
- Tenant config stored in Postgres `tenants` table
- Redis keys namespaced: `call:{tenant_id}:{call_sid}`
- pgvector partitioned by `tenant_id` for pricing isolation
- Separate LiveKit rooms per tenant (shared cluster)
- Azure Key Vault: one secret per tenant for FSM credentials

---

## 6. Component Ownership Map

```
voice-gateway/          → Voice Layer (LiveKit, Twilio, Deepgram, ElevenLabs)
agent-brain/            → Agent Pipeline (LangGraph, all 4 nodes)
pricing-service/        → Pricing Engine + Geo-routing
dispatch-adapter/       → ServiceTitan + HCP adapters
notification-service/   → Twilio SMS + email
shared/                 → Pydantic models, base clients, utilities
infra/                  → k8s, Terraform, CI/CD
```

---

## 7. Key Interfaces (Internal APIs)

### Voice Gateway → Agent Brain
```
WebSocket: ws://agent-brain/ws/call/{call_sid}
Message (text frame):
{
  "type": "transcript",
  "call_sid": "CA...",
  "tenant_id": "t_abc",
  "text": "My water heater is leaking",
  "is_final": true,
  "timestamp": 1718000000
}
```

### Agent Brain → Voice Gateway
```
WebSocket message:
{
  "type": "speak",
  "text": "I can have someone out in 2 hours. The estimate is $200–$450.",
  "call_sid": "CA..."
}
```

### Agent Brain → Dispatch Adapter
```
POST /jobs
{
  "tenant_id": "t_abc",
  "caller_name": "Ahmed Al-Rashid",
  "caller_phone": "+971501234567",
  "address": "123 Main Street, Dubai",
  "problem": "water heater leak",
  "urgency": "emergency",
  "estimate_min": 200,
  "estimate_max": 450,
  "preferred_window": "next_2_hours"
}
```

---

## Next: [02_Voice_Layer.Plan.md](./02_Voice_Layer.Plan.md)
