# Home Services Voice Agent

AI-powered inbound voice agent for home service businesses (roofers, plumbers, HVAC). Answers calls 24/7, extracts problem details from natural speech, quotes pricing, and books jobs into FSM systems.

See [docs/Plan.md](docs/Plan.md) for the full architecture and module plans.

---

## Module Progress

Status key: **Done** · **Partial** · **Not started**

| Module | Status | What's done | What's next |
|--------|--------|-------------|-------------|
| **Monorepo scaffold** | **Done** | `services/`, `shared/`, `infra/`, `tests/`, `docs/`, `.gitignore` | — |
| **Local dev stack** | **Done** | `docker-compose.dev.yml` — Postgres (pgvector), Redis, Azurite, 5 FastAPI services; `.env.dev.example` | Apply Alembic migrations on first boot |
| **Data layer** | **Partial** | Alembic `001_initial_schema` — `tenants`, `calls`, `conversation_turns`, `technicians`, `pricing_catalog` + pgvector extension | Redis session store, Azure Blob recording upload |
| **Voice gateway** | **Done** | Twilio SIP webhook, LiveKit room management, Deepgram STT, ElevenLabs TTS, barge-in, call lifecycle webhooks | WebSocket bridge to agent-brain |
| **Agent brain** | **Partial** | `AgentState` schema, 4 LangGraph nodes, pricing/geo tools, full `StateGraph`, prompts | `session_runner.py`, WebSocket API in `main.py`, LangSmith tracing |
| **Pricing service** | **Not started** | Health endpoint + Dockerfile stub | Vector embedding lookup, quote API |
| **Dispatch adapter** | **Not started** | Health endpoint + Dockerfile stub | ServiceTitan / Housecall Pro adapters |
| **Notification service** | **Not started** | Health endpoint + Dockerfile stub | Twilio SMS confirmation |
| **Shared** | **Partial** | `AgentState`, `DispatchClient` stub, `geo.py` stub | Real HTTP clients, embedding helpers |
| **Tests** | **Partial** | Unit + integration tests for voice-gateway and agent-brain pipeline | E2E simulated call flows |
| **CI/CD** | **Partial** | GitHub Actions — tests, linting, CodeQL, security | Service-specific install steps, fail on test errors |
| **Infra (AKS / Terraform)** | **Not started** | Placeholder `infra/` directories | Helm charts, Azure IaC, autoscaling |

---

## Service Details

### Voice Gateway (`services/voice-gateway`) — Done

Handles inbound Twilio SIP calls and the real-time voice pipeline.

| Component | File | Description |
|-----------|------|-------------|
| Twilio SIP | `twilio_sip.py` | TwiML generation for inbound call routing |
| LiveKit rooms | `room_manager.py` | Create / close per-call WebRTC rooms |
| STT | `stt_client.py` | Deepgram Nova streaming transcription |
| TTS | `tts_client.py` | ElevenLabs Turbo v2.5 chunked audio |
| Barge-in | `barge_in.py` | Interrupt TTS when caller speaks |
| Config | `config.py` | Pydantic Settings (API keys, LiveKit, SIP domain) |
| API | `main.py` | `/call/incoming`, `/call/status`, `/call/recording` |

**Tests:** `test_stt_client`, `test_tts_client`, `test_barge_in`, `test_room_manager`, `test_twilio_sip`, `test_config`, `test_voice_gateway` (integration)

---

### Agent Brain (`services/agent-brain`) — Partial

LangGraph pipeline that processes transcripts and drives the booking flow.

| Component | File | Description |
|-----------|------|-------------|
| State schema | `shared/models/agent_state.py` | `AgentState`, `UrgencyLevel`, `ServiceCategory`, `Technician` |
| Intent node | `nodes/intent_node.py` | Extract problem description and urgency |
| Entity node | `nodes/entity_node.py` | Extract address, caller name, service category |
| Qualifier node | `nodes/qualifier_node.py` | Confirm details with caller; `should_dispatch` routing |
| Dispatcher node | `nodes/dispatcher_node.py` | Book job via `DispatchClient` |
| Pricing tool | `tools/pricing_tool.py` | Quote lookup (stub client) |
| Geo tool | `tools/geo_tool.py` | Nearest technician routing (stub) |
| Prompts | `prompts/intents.py`, `prompts/responses.py` | LLM system prompts and spoken responses |
| Graph | `graph.py` | Full `StateGraph` with parallel pricing + geo edges |

**Graph flow:**

```
intent → entity → pricing ──┐
              └── geo_routing ──┴→ qualifier ──should_dispatch──┬→ dispatcher → END
                                                                ├→ clarify → qualifier
                                                                └→ re_ask → qualifier
```

**Tests:** `test_intent_node`, `test_entity_node`, `test_qualifier_node`, `test_dispatcher_node`, `test_tools`, `test_prompts`, `test_graph_flow` (integration)

**Not yet wired:** `main.py` (health only), `session_runner.py` (Redis multi-turn loop), agent-brain ↔ voice-gateway WebSocket

---

### Pricing Service (`services/pricing-service`) — Not started

Stub FastAPI app with `/health` only. Planned: pgvector similarity search over `pricing_catalog`, quote range API.

---

### Dispatch Adapter (`services/dispatch-adapter`) — Not started

Stub FastAPI app with `/health` only. Planned: ServiceTitan and Housecall Pro API adapters behind a dual-tenant interface.

---

### Notification Service (`services/notification-service`) — Not started

Stub FastAPI app with `/health` only. Planned: Twilio SMS booking confirmation to homeowner.

---

### Shared (`shared/`)

| Path | Status | Description |
|------|--------|-------------|
| `models/agent_state.py` | Done | Pydantic state schema shared across services |
| `clients/dispatch_client.py` | Stub | FSM booking client (returns mock responses) |
| `utils/geo.py` | Stub | Nearest technician lookup (returns mock data) |

---

### Data Layer

| Item | Status | Description |
|------|--------|-------------|
| `alembic/versions/001_initial_schema.py` | Done | 5 tables + pgvector extension |
| Redis session state | Not started | Per-call state across agent-brain pods |
| Azure Blob recordings | Not started | Dual-channel call recording storage |

---

## Repo Structure

```
agentic_voice_over/
├── docs/                           # Architecture and module plans
├── services/
│   ├── voice-gateway/              # LiveKit + Twilio SIP bridge       [Done]
│   ├── agent-brain/                # LangGraph pipeline                [Partial]
│   ├── pricing-service/            # Vector lookup + quote API         [Stub]
│   ├── dispatch-adapter/           # ServiceTitan / HCP connector      [Stub]
│   └── notification-service/       # Twilio SMS / email                [Stub]
├── shared/
│   ├── models/                     # Pydantic schemas (AgentState)     [Done]
│   ├── clients/                    # FSM, Twilio clients               [Stub]
│   └── utils/                      # Geo, embedding helpers            [Stub]
├── alembic/                        # Postgres migrations               [Done]
├── infra/                          # K8s, Terraform                    [Not started]
├── tests/
│   ├── unit/                       # Per-component tests               [Partial]
│   ├── integration/                # Cross-service tests               [Partial]
│   └── e2e/                        # Simulated call flows              [Not started]
└── docker-compose.dev.yml          # Local dev stack                   [Done]
```

---

## Local Development

```bash
# 1. Copy env template and fill in API keys
cp .env.dev.example .env.dev

# 2. Start all services
docker compose -f docker-compose.dev.yml up --build

# 3. Run migrations (first time)
alembic upgrade head

# 4. Run tests
pip install -r services/voice-gateway/requirements.txt
pip install -r services/agent-brain/requirements.txt
pip install pytest pytest-asyncio
pytest tests/unit tests/integration -v
```

| Service | Port | Health |
|---------|------|--------|
| voice-gateway | 8000 | `GET /health` |
| agent-brain | 8001 | `GET /health` |
| pricing-service | 8002 | `GET /health` |
| dispatch-adapter | 8003 | `GET /health` |
| notification-service | 8004 | `GET /health` |
| Postgres | 5432 | — |
| Redis | 6379 | — |
| Azurite (Blob) | 10000 | — |

---

## Documentation

| Doc | Covers |
|-----|----------|
| [Plan.md](docs/Plan.md) | Master plan and module index |
| [01_Architecture.Plan.md](docs/01_Architecture.Plan.md) | System layers and data flow |
| [02_Voice_Layer.Plan.md](docs/02_Voice_Layer.Plan.md) | STT, TTS, WebRTC, latency |
| [03_Agent_Pipeline.Plan.md](docs/03_Agent_Pipeline.Plan.md) | LangGraph nodes and state |
| [04_Pricing_Engine.Plan.md](docs/04_Pricing_Engine.Plan.md) | Vector DB and quote logic |
| [05_FSM_Integrations.Plan.md](docs/05_FSM_Integrations.Plan.md) | ServiceTitan / HCP APIs |
| [06_Data_Layer.Plan.md](docs/06_Data_Layer.Plan.md) | Postgres, Redis, Blob Storage |
| [07_Infra_DevOps.Plan.md](docs/07_Infra_DevOps.Plan.md) | AKS, CI/CD, autoscaling |
| [08_Observability.Plan.md](docs/08_Observability.Plan.md) | LangSmith, Prometheus |
| [09_Security_Compliance.Plan.md](docs/09_Security_Compliance.Plan.md) | Auth, PII, recording laws |
| [10_Milestones_Timeline.Plan.md](docs/10_Milestones_Timeline.Plan.md) | Phases and go-live checklist |
