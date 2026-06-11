# Home Services Voice Agent

AI-powered inbound phone agent for home service businesses (plumbers, HVAC, roofers, electrical). Answers calls 24/7, understands the problem in natural speech, quotes a price range, assigns a technician, and books the job into a field-service system — with SMS confirmation.

Full architecture and module plans: [docs/Plan.md](docs/Plan.md)

---

## What this project is

A **production-oriented, multi-tenant voice agent platform** — not a single-script demo. It is designed to replace a human receptionist for companies running Google Local Services Ads, where a missed call often means a lost $300–$3,000 job.

**End-to-end flow:**

```
Caller dials Twilio number
        │
        ▼
  voice-gateway          Deepgram STT + TTS, real-time audio
        │  WebSocket transcripts
        ▼
  agent-brain            LangGraph: intent → entities → quote → dispatch
        │
   ┌────┴────┐
   ▼         ▼
pricing-   dispatch-      ServiceTitan / Housecall Pro
service    adapter
   │         │
   └────┬────┘
        ▼
notification-service   Booking confirmation SMS
```

---

## Why this project is different

Most voice-AI tutorials wire **one tool** (LiveKit Agents, Vapi, Retell, or a single FastAPI + OpenAI Realtime file) straight to an LLM. This repo takes a different path on purpose:

| Typical demo / SaaS wrapper | This project |
|-----------------------------|--------------|
| One service does voice + brain | **Separated microservices** — voice, agent, pricing, dispatch, notifications scale independently |
| LLM guesses prices | **pgvector pricing engine** — semantic lookup over a per-tenant service catalog with fallback ranges |
| “Book an appointment” stub | **Real FSM adapters** — ServiceTitan + Housecall Pro behind a tenant-routed factory |
| Stateless chat | **LangGraph state machine** — parallel pricing + geo routing, qualification loops, conditional dispatch |
| Generic assistant | **Domain-specific graph** — urgency, service category, estimates, technician assignment, confirmation |
| Black-box hosted agent | **You own the stack** — swap STT/TTS/LLM, self-host on Azure (AKS), full recording + Postgres audit trail |
| LiveKit Agents worker only | **Custom voice path** — Twilio Media Streams *or* LiveKit SIP; agent-brain over WebSocket, not locked to one telephony SDK |

The goal is a **multi-tenant SaaS** a home-services company can white-label: each tenant gets their own pricing catalog, FSM connection, and business name — one phone number routes to `?tenant_id=…` on the webhook.

---

## What’s done so far

Status: **MVP in progress** — core paths implemented locally; production infra and observability still planned.

### Done

| Area | Status |
|------|--------|
| **Monorepo** | `services/`, `shared/`, `alembic/`, `tests/`, `docs/`, Docker Compose dev stack |
| **Voice gateway** | Twilio webhooks, **Media Streams** WebSocket path, LiveKit SIP path (optional), Deepgram STT, Deepgram/ElevenLabs TTS, barge-in, call lifecycle + recording hooks |
| **Agent brain** | LangGraph pipeline (intent → entity → pricing + geo → qualifier → dispatcher), `SessionRunner`, Redis session state, WebSocket API `/ws/call/{call_sid}` |
| **Pricing service** | pgvector catalog lookup, OpenAI embeddings, Redis cache, category fallbacks |
| **Dispatch adapter** | ServiceTitan + Housecall Pro adapters, factory routing, queue retry |
| **Notification service** | Twilio SMS booking confirmation |
| **Data layer** | Alembic migrations (`tenants`, `calls`, `conversation_turns`, `technicians`, `pricing_catalog`), Redis call state, Azurite recording upload |
| **Tests** | Unit + integration tests for voice pipeline, agent graph, pricing API, booking flow |
| **CI** | GitHub Actions — tests, linting, security, CodeQL |

### In progress / not started

| Area | Notes |
|------|--------|
| **LiveKit SIP in dev** | Works in code; Twilio SIP bridging is finicky — **Twilio Media Streams** is the recommended dev path |
| **Twilio trial** | Media Streams and SIP require a **paid** Twilio account; trial blocks `<Connect><Stream>` and `<Dial><Sip>` |
| **Production infra** | AKS, Terraform, Helm — placeholders in `infra/` |
| **Observability** | LangSmith wiring partial; Prometheus/Grafana not started |
| **E2E phone tests** | Automated simulated calls in CI not yet added |

---

## Quick start (local dev)

### Prerequisites

- Docker + Docker Compose
- API keys: **OpenAI**, **Deepgram**, **Twilio** (paid for live voice)
- [ngrok](https://ngrok.com) (free account) to expose `voice-gateway` to Twilio
- Optional: LiveKit Cloud account if using `VOICE_TRANSPORT=livekit_sip`

### 1. Configure environment

```bash
cp .env.dev.example .env.dev
```

Edit `.env.dev` with your keys. Minimum for a live call:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | LangGraph LLM + pricing embeddings |
| `DEEPGRAM_API_KEY` | Speech-to-text + TTS (Aura) |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | Phone webhooks |
| `BUSINESS_NAME` | Spoken greeting |
| `VOICE_TRANSPORT` | `twilio_stream` (recommended) or `livekit_sip` |
| `PUBLIC_BASE_URL` | Your ngrok **HTTPS** URL (no trailing slash) |

See [.env.dev.example](.env.dev.example) for LiveKit, ElevenLabs, and Postgres settings.

### 2. Start services

```bash
docker compose -f docker-compose.dev.yml up --build
```

### 3. Run database migrations

From the host (not inside Docker):

```bash
pip install -r requirements-dev.txt
export POSTGRES_DSN="postgresql://devuser:devpass@localhost:5432/voice_agent_dev"
alembic upgrade head
```

### 4. Expose voice-gateway to Twilio

```bash
ngrok http 8000
```

Copy the `https://….ngrok-free.app` URL into `.env.dev`:

```bash
PUBLIC_BASE_URL="https://your-subdomain.ngrok-free.app"
```

Restart voice-gateway:

```bash
docker compose -f docker-compose.dev.yml up -d voice-gateway
```

### 5. Configure Twilio phone number

**Phone Numbers → your number → Voice → A call comes in → Webhook (POST):**

```
https://your-subdomain.ngrok-free.app/call/incoming?tenant_id=t_test
```

Replace `t_test` with your tenant ID when you have real tenant records in Postgres.

### 6. Call your number

Dial your Twilio number from a **verified** caller ID (trial accounts require verified numbers). You should hear the greeting, then be able to describe a problem and get a quote-driven response.

**Health checks:**

| Service | URL |
|---------|-----|
| voice-gateway | http://localhost:8000/health |
| agent-brain | http://localhost:8001/health |
| pricing-service | http://localhost:8002/health |

### 7. Run tests

```bash
pip install -r services/voice-gateway/requirements.txt \
            -r services/agent-brain/requirements.txt \
            -r requirements-dev.txt
pytest tests/unit tests/integration -v
```

---

## Voice transport modes

Set `VOICE_TRANSPORT` in `.env.dev`:

### `twilio_stream` (recommended for local dev)

```
Twilio → <Connect><Stream> → voice-gateway /ws/media → Deepgram + agent-brain
```

- No LiveKit required for the phone leg
- Requires **paid Twilio** (Media Streams blocked on trial)
- Set `PUBLIC_BASE_URL` to your ngrok HTTPS URL

### `livekit_sip` (production-style)

```
Twilio → <Dial><Sip> → LiveKit room ← voice-gateway bot (WebRTC)
```

- Needs `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_SIP_DOMAIN`, `LIVEKIT_SIP_TRUNK_ID`
- Run once: `python scripts/setup_livekit_sip_dispatch.py` (with env loaded)
- SIP uses `;transport=tls` for Twilio compatibility

---

## Service map

| Service | Port | Role |
|---------|------|------|
| **voice-gateway** | 8000 | Telephony webhooks, audio I/O, STT/TTS loop |
| **agent-brain** | 8001 | LangGraph agent, per-call WebSocket |
| **pricing-service** | 8002 | pgvector quote lookup |
| **dispatch-adapter** | 8003 | FSM job creation |
| **notification-service** | 8004 | SMS confirmations |
| Postgres (pgvector) | 5432 | Tenants, calls, pricing catalog |
| Redis | 6379 | Per-call agent state |
| Azurite | 10000 | Local Blob Storage for recordings |

---

## Repo structure

```
agentic_voice_over/
├── docs/                    # Architecture and module plans
├── services/
│   ├── voice-gateway/       # Twilio, STT/TTS, LiveKit bot
│   ├── agent-brain/         # LangGraph + SessionRunner
│   ├── pricing-service/     # Vector pricing lookup
│   ├── dispatch-adapter/    # ServiceTitan / Housecall Pro
│   └── notification-service/# Twilio SMS
├── shared/                  # AgentState, DB/Redis clients, dispatch client
├── alembic/                 # Postgres migrations
├── scripts/                 # LiveKit SIP setup helper
├── tests/                   # unit/, integration/, e2e/
└── docker-compose.dev.yml
```

---

## Agent graph (simplified)

```
intent → entity → pricing ──┐
              └── geo ──────┴→ qualifier ──should_dispatch──┬→ dispatcher → END
                                                           ├→ clarify → qualifier
                                                           └→ re_ask → qualifier
```

The agent extracts problem, address, and urgency; fetches a price range and nearest technician in parallel; confirms with the caller; then books via the dispatch adapter and triggers SMS.

---

## Twilio trial limitations

If calls fail with “recharge” or “upgrade”:

1. **Verify your caller phone** in [Twilio Console → Verified Caller IDs](https://console.twilio.com/us1/develop/phone-numbers/manage/verified)
2. **Upgrade to a paid account** — trial blocks Media Streams (`<Connect><Stream>`) and SIP dial (`<Dial><Sip>`), which this project uses for live voice
3. Check [Monitor → Calls](https://console.twilio.com/us1/monitor/logs/calls) for error codes

You can still run `pytest tests/integration/test_booking_flow.py` without Twilio.

---

## Documentation

| Doc | Covers |
|-----|--------|
| [Plan.md](docs/Plan.md) | Master plan and module index |
| [01_Architecture.Plan.md](docs/01_Architecture.Plan.md) | System layers and data flow |
| [02_Voice_Layer.Plan.md](docs/02_Voice_Layer.Plan.md) | STT, TTS, WebRTC, latency |
| [03_Agent_Pipeline.Plan.md](docs/03_Agent_Pipeline.Plan.md) | LangGraph nodes and state |
| [04_Pricing_Engine.Plan.md](docs/04_Pricing_Engine.Plan.md) | Vector DB and quote logic |
| [05_FSM_Integrations.Plan.md](docs/05_FSM_Integrations.Plan.md) | ServiceTitan / Housecall Pro |
| [06_Data_Layer.Plan.md](docs/06_Data_Layer.Plan.md) | Postgres, Redis, Blob Storage |
| [10_Milestones_Timeline.Plan.md](docs/10_Milestones_Timeline.Plan.md) | Phases and go-live checklist |

---

## License

Private / internal — see repository owner for usage terms.
