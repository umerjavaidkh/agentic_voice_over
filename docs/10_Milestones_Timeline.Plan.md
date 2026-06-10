# 10 — Milestones & Timeline Plan

**Total estimated build time (solo or 2-person team):** 12–16 weeks to production  
**MVP target:** 6 weeks (bookings working end-to-end for one tenant)  

---

## 1. Phase Overview

```
Phase 1: Foundation          Weeks 1–2
Phase 2: Voice Pipeline      Weeks 3–4
Phase 3: Agent Brain         Weeks 4–6
Phase 4: Integrations        Weeks 6–8
Phase 5: Hardening           Weeks 8–10
Phase 6: Beta & Launch       Weeks 10–12
Phase 7: Scale               Weeks 12–16
```

---

## 2. Phase 1 — Foundation (Weeks 1–2)

**Goal:** Dev environment running. Core infra provisioned. CI/CD green.

### Deliverables
- [ ] Monorepo structure created (matches [Plan.md](./Plan.md))
- [ ] AKS cluster provisioned via Terraform
- [ ] Postgres + Redis + Service Bus provisioned on Azure
- [ ] Azure Container Registry set up
- [ ] GitHub Actions pipeline: lint → test → build → push to ACR
- [ ] Key Vault secrets seeded for all services
- [ ] Postgres schema migrations run (all 5 tables)
- [ ] `pgvector` extension enabled and `pricing_catalog` table created
- [ ] Shared Pydantic models (`AgentState`, `JobPayload`, etc.) defined
- [ ] Structured logging configured for all services
- [ ] Prometheus + Grafana deployed to monitoring namespace
- [ ] LangSmith project created, test trace verified

### Exit criteria
- A test FastAPI pod deploys to AKS from CI/CD in < 5 minutes
- Postgres accepts connections, all migrations applied
- Redis connectivity verified from within cluster

---

## 3. Phase 2 — Voice Pipeline (Weeks 3–4)

**Goal:** Caller can call a Twilio number, talk to the bot, hear a response.

### Deliverables
- [ ] Twilio number purchased + webhook configured
- [ ] LiveKit server deployed (self-hosted or LiveKit Cloud)
- [ ] SIP trunk configured: Twilio → LiveKit
- [ ] `voice-gateway` service:
  - [ ] Twilio webhook handler (`/call/incoming`, `/call/status`)
  - [ ] LiveKit room creation on call start
  - [ ] Deepgram WebSocket streaming connected to caller audio track
  - [ ] ElevenLabs TTS streaming connected to bot audio track
  - [ ] Barge-in detection working
- [ ] Hardcoded greeting plays (no AI yet — just TTS test)
- [ ] Call recording uploaded to Azure Blob Storage on call end
- [ ] `active_calls_count` metric visible in Grafana

### Exit criteria
- Call test number → hear greeting → speak → hear echo of speech (parrot test)
- STT transcript appears in logs within 400ms of speech
- TTS audio plays within 800ms of text being sent

---

## 4. Phase 3 — Agent Brain (Weeks 4–6)

**Goal:** Four-node LangGraph graph working. Full conversation flow in staging.

### Deliverables
- [ ] `agent-brain` service scaffolded with FastAPI + WebSocket endpoint
- [ ] `AgentState` Pydantic model finalized
- [ ] `IntentNode` implemented + tested (50 sample phrases)
- [ ] `EntityNode` implemented (multi-turn address collection)
- [ ] `QualifierNode` implemented (emergency vs scheduled routing)
- [ ] `DispatcherNode` implemented (mock FSM call for now)
- [ ] `PricingTool` implemented (with pgvector lookup)
- [ ] `GeoRoutingTool` implemented (mock technician data for now)
- [ ] LangGraph graph assembled + conditional edges tested
- [ ] Redis session persistence: state survives pod restart
- [ ] Agent Brain ↔ Voice Gateway WebSocket integration
- [ ] Full conversation flow (greeting → problem → address → estimate → confirm) works end-to-end in staging
- [ ] LangSmith traces visible for every graph invocation

### Exit criteria
- Test call: "My AC stopped working" → agent asks address → agent gives estimate → agent asks to confirm
- LangGraph graph latency p95 < 1.2s (measured via Prometheus)
- State correctly persisted between turns in Redis

---

## 5. Phase 4 — Integrations (Weeks 6–8)

**Goal:** Real bookings land in ServiceTitan and/or Housecall Pro. SMS confirms.

### Deliverables
- [ ] Pricing catalog seeded for first pilot tenant (50+ entries)
- [ ] Pricing vector embeddings generated (OpenAI text-embedding-3-small)
- [ ] Pricing lookup API tested: ≥ 0.75 confidence on 80% of test queries
- [ ] `dispatch-adapter` service built:
  - [ ] ServiceTitan adapter: auth + create_job + get_available_technicians
  - [ ] Housecall Pro adapter (if needed for pilot tenant)
  - [ ] Adapter factory (tenant → correct FSM)
- [ ] Azure Service Bus retry queue for failed dispatches
- [ ] `notification-service`: Twilio SMS confirmation working
- [ ] First tenant config seeded in Key Vault
- [ ] First real booking created in staging ServiceTitan sandbox
- [ ] Tenant onboarding runbook documented

### Exit criteria
- Live test: call → full conversation → real job appears in ServiceTitan → SMS arrives on test phone
- Dispatch latency < 3s (ServiceTitan API round-trip)
- Failed dispatch retried within 60 seconds via Service Bus

---

## 6. Phase 5 — Hardening (Weeks 8–10)

**Goal:** System survives real load, failures, and edge cases.

### Deliverables
- [ ] Fallback flows implemented:
  - [ ] STT failure → prompt caller to repeat × 2 → fallback message
  - [ ] LLM API error → scripted fallback → lead capture SMS
  - [ ] FSM API down → queue job, notify business owner
- [ ] Prompt injection sanitizer active on all incoming transcripts
- [ ] Recording consent disclosure for two-party states
- [ ] PII masking verified in all log outputs
- [ ] Load test: 20 simultaneous calls, all complete < 5min
- [ ] HPA tested: pods scale up under load, scale down after
- [ ] All Prometheus alert rules firing correctly on simulated failures
- [ ] Grafana operations dashboard complete
- [ ] Grafana business dashboard complete
- [ ] Security review:
  - [ ] Twilio webhook signature verification active
  - [ ] All secrets in Key Vault (zero in env files)
  - [ ] mTLS between pods via Linkerd
  - [ ] Trivy image scan passing in CI

### Exit criteria
- Chaos test: kill one pod mid-call → no data loss, call gracefully fails over
- 20 concurrent call load test: < 2% error rate, p95 latency < 1.5s
- Zero PII visible in raw log output

---

## 7. Phase 6 — Beta & Launch (Weeks 10–12)

**Goal:** 2–3 real businesses on the system, collecting real calls, real revenue.

### Deliverables
- [ ] Pilot tenant 1 onboarded (plumbing company)
- [ ] Pilot tenant 2 onboarded (HVAC company)
- [ ] Pilot tenant 3 onboarded (roofing company)
- [ ] Business owner dashboard (basic — Grafana embed or simple web UI):
  - Today's calls, bookings, conversion rate, missed revenue
- [ ] Weekly email report to business owners
- [ ] SLA agreement: 99.9% uptime, < 5% missed call rate
- [ ] Support runbook for common issues
- [ ] Billing/pricing model implemented:
  - $0.15/min for handled calls OR
  - $49/month flat + $30/booked job (commission model)

### Exit criteria
- 3 tenants live, each receiving 5+ calls/day
- > 65% conversion rate (calls → bookings) in first week
- Zero critical incidents (P1) in first 2 weeks

---

## 8. Phase 7 — Scale (Weeks 12–16)

**Goal:** Ready to onboard 50+ tenants, multi-region, self-serve onboarding.

### Deliverables
- [ ] Self-serve tenant onboarding UI (web form → provisions tenant config automatically)
- [ ] Automatic pricing catalog generation from ServiceTitan/HCP job history
- [ ] Multi-language support (Spanish, Arabic — second Deepgram + ElevenLabs model per language)
- [ ] A/B test framework for agent scripts (which phrasing converts better?)
- [ ] Custom voice cloning per tenant (their own voice)
- [ ] Multi-region deployment (US + UAE/Middle East)
- [ ] White-label option (agent says business name, not "AI assistant")
- [ ] Outbound call capability (follow up on missed leads)

---

## 9. MVP Definition (Week 6 exit)

The absolute minimum that generates real business value:

| Feature | In MVP? |
|---------|---------|
| Answer call and greet | ✅ |
| Extract problem description | ✅ |
| Ask for address | ✅ |
| Provide price estimate | ✅ |
| Emergency vs scheduled routing | ✅ |
| Book job in ServiceTitan | ✅ |
| SMS confirmation to caller | ✅ |
| Basic Grafana dashboard | ✅ |
| Housecall Pro support | ❌ Phase 4 |
| Multi-language | ❌ Phase 7 |
| Business owner web UI | ❌ Phase 6 |
| Outbound calls | ❌ Phase 7 |

---

## 10. Go-Live Checklist

Run this before flipping Twilio to production:

### Systems
- [ ] All 5 services running in `voice-agent-prod` namespace
- [ ] All HPAs configured and tested
- [ ] Prometheus alerts connected to PagerDuty (or Slack #on-call)
- [ ] LangSmith project set to production
- [ ] Azure Blob Lifecycle Management policies applied (90d recordings, 1y transcripts)
- [ ] Key Vault access policies verified for all pods

### Voice
- [ ] Production Twilio number pointed to prod Voice Gateway
- [ ] Deepgram: production API key with rate limit of 50 concurrent streams
- [ ] ElevenLabs: production plan supporting concurrent TTS
- [ ] Test call from real phone: full flow completes

### Data
- [ ] Pricing catalog for tenant has ≥ 30 entries
- [ ] pgvector index built on pricing_catalog
- [ ] At least 5 technicians seeded in technicians table
- [ ] Tenant config in Key Vault verified

### Legal
- [ ] Recording consent disclosure active (if required in tenant's state)
- [ ] Privacy policy updated to include AI call handling
- [ ] Terms of service updated

### Business
- [ ] Business owner has been walked through the Grafana dashboard
- [ ] Support email/Slack channel established
- [ ] Rollback plan: if conversion rate < 30% in first 48h, disable AI, forward to human

---

## 11. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Deepgram accuracy low for accents | Medium | High | Test with diverse callers, fallback to clarify prompt |
| ServiceTitan API rate limits | Low | High | Implement rate limiter, retry queue |
| LLM cost overrun | Medium | Medium | Set hard token limit per call (500 tokens/turn max) |
| Caller hangs up on AI | High | Medium | Tune greeting to feel human-like, offer "press 1 for human" escape hatch |
| ServiceTitan API changes | Low | High | Adapter pattern isolates impact to one file |
| TCPA violation (US) | Low | Critical | Recording consent implemented, legal review done |
| LLM hallucinating prices | Medium | High | Price always comes from pgvector, never from LLM |

---

## 12. Budget Breakdown — Dev → Staging → Production

### Dev Phase (local Docker Compose, no cloud compute)

| Service | Cost |
|---------|------|
| Twilio trial credit | $0 ($15 free) |
| Deepgram | $0 ($200 free credit on signup) |
| ElevenLabs | $0 (10k chars/mo free) |
| OpenAI GPT-4o-mini | ~$2–5 (test calls only) |
| LiveKit | $0 (10k min/mo free cloud, or self-host) |
| Azure Postgres (local Docker) | $0 |
| Azure Redis (local Docker) | $0 |
| Azure Blob (local Azurite emulator) | $0 |
| **Total dev** | **~$2–5/month** |

### Staging Phase (Azure $200 free credit, 30 days)

| Service | Est. spend from $200 credit |
|---------|----------------------------|
| Azure DB for PostgreSQL Flexible (B1ms) | $0 — covered by 12-mo free tier (750 hrs) |
| Azure Blob Storage | $0 — covered by 12-mo free tier (5 GB) |
| Azure Cache for Redis (C0 Basic) | ~$16 |
| AKS nodes (2× B2s VMs, 30 days) | ~$60 |
| Azure Service Bus + Key Vault | $0 — always-free tiers |
| Azure Monitor (log ingestion) | $0 — 5 GB/mo free |
| Bandwidth + misc | ~$10 |
| **Total from $200 credit** | **~$86 spent — $114 remaining** |

> **Tip:** Skip AKS during staging — run all 5 services on a single B2s VM with Docker Compose. Spend drops to ~$26 total, leaving $174 credit for production ramp-up.

### Production Phase (per month at scale, 1,000 calls/month, Azure-only)

| Service | Cost estimate |
|---------|-------------|
| Twilio (minutes + SMS) | ~$150 |
| Deepgram Nova-3 (streaming) | ~$80 |
| ElevenLabs Turbo | ~$120 |
| OpenAI GPT-4o-mini (tokens) | ~$40 |
| LiveKit Cloud | ~$50 |
| AKS (3× Standard_D4s_v5 nodes) | ~$600 |
| Azure DB for PostgreSQL Flexible (GP tier) | ~$120 |
| Azure Cache for Redis (C2 Standard) | ~$90 |
| Azure Blob Storage (recordings + logs) | ~$15 |
| Azure Service Bus (Standard) | ~$10 |
| Azure Key Vault | ~$5 |
| LangSmith Pro | $39 |
| **Total production** | **~$1,319/month** |

At $49/month + $30/booking, with 1,000 calls at 70% conversion (700 bookings):
- Revenue: $49 × N_tenants + $30 × 700 = depends on tenant count
- Break-even: ~3 tenants at 700 bookings each

### Azure Free Credit Strategy

```
Month 0 (Dev):     Local Docker only        → ~$5 total
Month 1 (Staging): $200 credit, AKS light   → ~$86 from credit
Month 2–12:        12-mo free tiers kick in  → Postgres + Blob = $0
                   Pay only: Redis + AKS nodes
Month 12+:         Full pay-as-you-go        → ~$1,319/mo at scale
```

---

> **You're ready to build.** Start with [01_Architecture.Plan.md](./01_Architecture.Plan.md) and work top-down.
