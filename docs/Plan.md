# 🏠 Home Services Voice Agent — Master Plan

## Project Overview

An AI-powered inbound voice agent for home service businesses (roofers, plumbers, HVAC) that:
- Answers calls 24/7 with sub-800ms latency
- Extracts problem, address, urgency from natural speech
- Queries a pricing vector DB to give real-time estimate ranges
- Books and dispatches jobs directly into ServiceTitan / Housecall Pro
- Sends SMS confirmation to the homeowner

---

## Problem Statement

Home service companies spend $2,000–$10,000/month on Google Local Services Ads.
If a human doesn't answer within **~100 seconds**, the homeowner clicks the next competitor.
A missed call = a missed job = $300–$3,000 in lost revenue — every single time.

This system turns ad spend into confirmed, dispatched jobs 24/7 with zero receptionist overhead.

---

## Module Index

| # | Plan File | Covers |
|---|-----------|--------|
| 1 | [01_Architecture.Plan.md](./01_Architecture.Plan.md) | System layers, data flow, component map |
| 2 | [02_Voice_Layer.Plan.md](./02_Voice_Layer.Plan.md) | STT, TTS, WebRTC, latency targets |
| 3 | [03_Agent_Pipeline.Plan.md](./03_Agent_Pipeline.Plan.md) | LangGraph nodes, state schema, tool calls |
| 4 | [04_Pricing_Engine.Plan.md](./04_Pricing_Engine.Plan.md) | Vector DB, embedding strategy, quote logic |
| 5 | [05_FSM_Integrations.Plan.md](./05_FSM_Integrations.Plan.md) | ServiceTitan & Housecall Pro API contracts |
| 6 | [06_Data_Layer.Plan.md](./06_Data_Layer.Plan.md) | Postgres schema, Redis session, Azure Blob Storage, pgvector |
| 7 | [07_Infra_DevOps.Plan.md](./07_Infra_DevOps.Plan.md) | FastAPI, AKS, autoscaling, CI/CD |
| 8 | [08_Observability.Plan.md](./08_Observability.Plan.md) | LangSmith, Prometheus, Grafana, alerting |
| 9 | [09_Security_Compliance.Plan.md](./09_Security_Compliance.Plan.md) | Auth, PII handling, call recording laws |
| 10 | [10_Milestones_Timeline.Plan.md](./10_Milestones_Timeline.Plan.md) | Phases, MVP scope, go-live checklist |

---

## High-Level Architecture

```
Inbound Call (Twilio SIP)
        │
        ▼
 ┌─────────────────────────────────────────┐
 │           VOICE LAYER                   │
 │  Deepgram STT ──► LiveKit ──► ElevenLabs TTS │
 └──────────────┬──────────────────────────┘
                │ transcript (streaming)
                ▼
 ┌─────────────────────────────────────────┐
 │        AGENT BRAIN (LangGraph)          │
 │                                         │
 │  IntentNode → EntityNode → QualifierNode → DispatcherNode │
 │              └── Shared State ──────────┘
 └──────────────┬──────────────────────────┘
        ┌───────┴────────┐
        ▼                ▼
 Pricing Engine     Geo-Routing
 (pgvector)         (Google Maps)
        │                │
        └───────┬────────┘
                ▼
 ┌─────────────────────────────────────────┐
 │        FSM INTEGRATIONS                 │
 │  ServiceTitan API / Housecall Pro API   │
 │  + Twilio SMS confirmation              │
 └─────────────────────────────────────────┘
```

---

## Core Technology Decisions

> **Cloud:** 100% Azure stack — Azure $200 free credit account. No AWS services used anywhere.

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Voice transport | LiveKit (WebRTC) | Open-source, self-hostable, <200ms audio path |
| STT | Deepgram Nova-3 | Streaming, lowest WER in noisy environments |
| TTS | ElevenLabs Turbo v2.5 | Chunk streaming, most natural prosody |
| Agent framework | LangGraph | Stateful graph with conditional edges, matches your existing stack |
| LLM backbone | GPT-4o-mini / Claude Haiku | Low-latency, cost-efficient for tool calling |
| Pricing DB | pgvector (Postgres) | Co-located with job DB, no extra infra |
| Session state | Redis | Sub-ms read for per-call state across pods |
| Backend runtime | FastAPI (async) | Native async WebSocket, matches your IntelliFlow stack |
| FSM | ServiceTitan + Housecall Pro | Dual adapter pattern for multi-tenant SaaS |
| Recording storage | Azure Blob Storage | S3 equivalent, native Azure, 5 GB free 12 months, Lifecycle policies built-in |
| Infra | AKS + Azure Service Bus | Full Azure-native stack, $200 free credit covers dev + staging |
| Tracing | LangSmith | Native LangGraph integration |

---

## Non-Functional Requirements

| Metric | Target |
|--------|--------|
| Call answer time (TTFB audio) | < 800ms |
| STT → LLM → TTS round-trip | < 1.2s p95 |
| Booking success rate | > 95% |
| System uptime | 99.9% |
| Max concurrent calls per tenant | 50 |
| PII retention | 90 days max, encrypted at rest |
| Call recording storage | Azure Blob Storage + AES-256 (Azure-managed keys) |

---

## Repo Structure (Monorepo)

```
voice-agent-home-services/
├── Plan.md                         ← you are here
├── 01_Architecture.Plan.md
├── 02_Voice_Layer.Plan.md
├── 03_Agent_Pipeline.Plan.md
├── 04_Pricing_Engine.Plan.md
├── 05_FSM_Integrations.Plan.md
├── 06_Data_Layer.Plan.md
├── 07_Infra_DevOps.Plan.md
├── 08_Observability.Plan.md
├── 09_Security_Compliance.Plan.md
├── 10_Milestones_Timeline.Plan.md
│
├── services/
│   ├── voice-gateway/              ← LiveKit + Twilio SIP bridge
│   ├── agent-brain/                ← LangGraph pipeline (FastAPI)
│   ├── pricing-service/            ← Vector lookup + quote API
│   ├── dispatch-adapter/           ← ServiceTitan / HCP connector
│   └── notification-service/       ← Twilio SMS / email
│
├── infra/
│   ├── k8s/                        ← Helm charts, AKS manifests
│   ├── terraform/                  ← Azure infra-as-code
│   └── docker/                     ← Dockerfiles per service
│
├── shared/
│   ├── models/                     ← Pydantic schemas (shared state)
│   ├── clients/                    ← ServiceTitan, HCP, Twilio clients
│   └── utils/                      ← Geo, embedding helpers
│
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/                        ← Simulated call flows
```

---

## Team Roles (when scaling)

| Role | Owns |
|------|------|
| Voice/AI Engineer | Voice layer, LangGraph agents |
| Backend Engineer | FastAPI services, data layer |
| Integration Engineer | ServiceTitan / HCP adapters |
| DevOps/Infra | AKS, Terraform, CI/CD |
| QA | Call simulation, booking flow tests |

---

> **Start reading:** [01_Architecture.Plan.md](./01_Architecture.Plan.md)
