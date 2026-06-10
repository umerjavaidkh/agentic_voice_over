# 08 — Observability Plan

**Tools:** LangSmith · Prometheus · Grafana · Azure Monitor  
**Philosophy:** "You can't improve what you can't measure." Every dollar of missed revenue is traceable.  

---

## 1. Three Observability Pillars

| Pillar | Tool | Answers |
|--------|------|---------|
| **Agent traces** | LangSmith | Which node failed? Which LLM call was slow? What did the agent say? |
| **System metrics** | Prometheus + Grafana | Is the system healthy? What's p95 latency? How many concurrent calls? |
| **Business metrics** | Custom Grafana dashboard | Conversion rate, revenue captured, missed calls, avg estimate |

---

## 2. LangSmith — Agent Tracing

Every LangGraph invocation produces a trace in LangSmith automatically.

### What each trace shows
- Full `AgentState` at each node (before + after)
- LLM call: prompt, response, token count, latency
- Tool calls: input, output, latency
- Edge decisions: which conditional branch was taken
- Total graph latency (entry → exit)

### Custom metadata tagging

```python
# services/agent-brain/graph.py

from langsmith import traceable
from langchain_core.tracers.context import tracing_v2_enabled

async def run_graph_with_tracing(state: AgentState, call_sid: str) -> AgentState:
    with tracing_v2_enabled(project_name="voice-agent-home-services"):
        result = await graph.ainvoke(
            state,
            config={
                "metadata": {
                    "call_sid": call_sid,
                    "tenant_id": state.tenant_id,
                    "caller_phone": state.caller_phone,
                    "service_category": str(state.service_category),
                    "urgency": str(state.urgency_level),
                    "turn_count": state.turn_count,
                }
            }
        )
    return result
```

### LangSmith evaluators (automated quality checks)

```python
# tests/evaluators/agent_quality.py

from langsmith.evaluation import evaluate, LangChainStringEvaluator

# Check: did the agent always ask for address before booking?
def check_address_collected(run, example):
    state = run.outputs["state"]
    if state["booking_confirmed"]:
        assert state["address"] is not None, "Booked without address!"
    return {"score": 1 if state.get("address") else 0}

# Check: did the agent stay on topic?
relevance_evaluator = LangChainStringEvaluator(
    "criteria",
    config={"criteria": "Is the agent response relevant to home service scheduling?"},
    prepare_data=lambda run, example: {
        "prediction": run.outputs["agent_response"],
        "input": run.inputs["user_text"],
    }
)
```

---

## 3. Prometheus Metrics

### 3.1 Custom metrics in each service

```python
# shared/metrics.py

from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Voice Gateway metrics
ACTIVE_CALLS = Gauge(
    "active_calls_count",
    "Number of currently active calls",
    ["tenant_id"]
)
CALL_DURATION = Histogram(
    "call_duration_seconds",
    "Total call duration",
    ["tenant_id", "outcome"],
    buckets=[30, 60, 120, 180, 300, 600]
)
STT_LATENCY = Histogram(
    "stt_latency_ms",
    "Deepgram STT latency (final transcript)",
    buckets=[50, 100, 200, 300, 500, 1000]
)
TTS_TTFB = Histogram(
    "tts_ttfb_ms",
    "ElevenLabs time-to-first-audio-byte",
    buckets=[100, 200, 300, 500, 800, 1500]
)

# Agent Brain metrics
GRAPH_LATENCY = Histogram(
    "agent_graph_latency_ms",
    "Full LangGraph invocation latency",
    ["tenant_id", "outcome_node"],
    buckets=[200, 400, 600, 800, 1200, 2000, 5000]
)
LLM_TOKEN_USAGE = Counter(
    "llm_tokens_total",
    "Total LLM tokens used",
    ["model", "node_name", "type"]    # type: input|output
)
TOOL_CALL_LATENCY = Histogram(
    "tool_call_latency_ms",
    "Individual tool call latency",
    ["tool_name"],
    buckets=[10, 30, 50, 100, 200, 500]
)

# Business metrics
BOOKINGS_TOTAL = Counter(
    "bookings_total",
    "Total confirmed bookings",
    ["tenant_id", "service_category", "urgency"]
)
MISSED_CALLS_TOTAL = Counter(
    "missed_calls_total",
    "Calls that ended without booking",
    ["tenant_id", "reason"]          # reason: fallback|abandoned|error
)
ESTIMATED_REVENUE = Counter(
    "estimated_revenue_dollars_total",
    "Sum of max estimate for booked jobs",
    ["tenant_id", "service_category"]
)
PRICING_CONFIDENCE = Histogram(
    "pricing_confidence_score",
    "Confidence score of pricing lookups",
    buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# FSM metrics
FSM_API_LATENCY = Histogram(
    "fsm_api_latency_ms",
    "Latency of FSM API calls",
    ["fsm_type", "operation"],
    buckets=[100, 300, 500, 1000, 2000, 5000]
)
FSM_API_ERRORS = Counter(
    "fsm_api_errors_total",
    "FSM API errors",
    ["fsm_type", "error_type"]
)
```

### 3.2 Metric instrumentation in voice gateway

```python
# Usage in voice-gateway/call_session.py

import time
from shared.metrics import ACTIVE_CALLS, CALL_DURATION, TTS_TTFB

class CallSession:
    async def start(self, tenant_id: str):
        self.start_time = time.time()
        ACTIVE_CALLS.labels(tenant_id=tenant_id).inc()

    async def end(self, tenant_id: str, outcome: str):
        duration = time.time() - self.start_time
        ACTIVE_CALLS.labels(tenant_id=tenant_id).dec()
        CALL_DURATION.labels(tenant_id=tenant_id, outcome=outcome).observe(duration)
```

---

## 4. Grafana Dashboards

### 4.1 Operations Dashboard

**Panel 1: System Health**
```
Active calls by tenant (Gauge)
CPU/Memory by service (Time series)
Pod restarts last 24h (Stat)
```

**Panel 2: Voice Layer Performance**
```
STT latency p50/p95/p99 (Time series)
TTS TTFB p50/p95 (Time series)
Deepgram WebSocket disconnects (Counter)
```

**Panel 3: Agent Performance**
```
LangGraph p50/p95 latency (Time series)
LLM token usage/hour (Bar chart)
Tool call latency by tool (Heatmap)
```

**Panel 4: FSM Integration Health**
```
ServiceTitan API success rate (Gauge)
Housecall Pro API success rate (Gauge)
Failed dispatch queue depth (Gauge)
FSM API latency p95 (Time series)
```

### 4.2 Business Dashboard

```
Bookings/hour (Time series)
Conversion rate by tenant (Bar chart — bookings/total calls)
Missed calls by reason (Pie chart)
Estimated revenue captured today (Big stat)
Average estimate by service category (Table)
Pricing confidence distribution (Histogram)
```

---

## 5. Alerting Rules

```yaml
# infra/prometheus/alerts.yaml

groups:
- name: voice-agent-critical
  rules:

  - alert: HighCallDropRate
    expr: |
      rate(missed_calls_total{reason="error"}[5m]) > 0.1
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "High call error rate — {{ $value }} errors/sec"
      runbook: "Check agent-brain logs. May be LLM API outage."

  - alert: TTS_TTFB_High
    expr: |
      histogram_quantile(0.95, rate(tts_ttfb_ms_bucket[5m])) > 1200
    for: 3m
    labels:
      severity: warning
    annotations:
      summary: "TTS p95 TTFB above 1.2s — callers hearing dead air"

  - alert: FSM_API_Down
    expr: |
      rate(fsm_api_errors_total[5m]) > 0.5
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "FSM API error rate high — bookings may be failing"

  - alert: DispatchQueueBuildup
    expr: |
      azure_servicebus_queue_message_count{queue="failed-dispatch"} > 20
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "{{ $value }} jobs stuck in retry queue"

  - alert: LangGraphLatencyHigh
    expr: |
      histogram_quantile(0.95, rate(agent_graph_latency_ms_bucket[5m])) > 3000
    for: 3m
    labels:
      severity: warning
    annotations:
      summary: "Agent thinking time > 3s p95 — degraded caller experience"

  - alert: PodCrashLooping
    expr: |
      rate(kube_pod_container_status_restarts_total[15m]) > 0
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Pod {{ $labels.pod }} is crash-looping"
```

---

## 6. Structured Logging

All services emit JSON-structured logs. No unstructured print statements.

```python
# shared/utils/logger.py

import structlog
import logging

def configure_logging(service_name: str):
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.WriteLoggerFactory(),
    )

logger = structlog.get_logger()

# Usage:
logger.info("call_started",
    call_sid="CA...",
    tenant_id="t_abc",
    caller_phone="+1...",
)

logger.error("fsm_api_failed",
    call_sid="CA...",
    fsm_type="servicetitan",
    error=str(e),
    retry_count=3,
)
```

All logs → Azure Monitor Log Analytics workspace. Queries via KQL.

---

## 7. Key KPIs to Track Weekly

| KPI | Target | Alert if |
|-----|--------|---------|
| Call → booking conversion | > 70% | < 50% |
| p95 TTFB (call answer to audio) | < 800ms | > 1.5s |
| p95 agent turn latency | < 1.5s | > 3s |
| FSM booking success rate | > 98% | < 90% |
| Pricing confidence avg | > 0.75 | < 0.6 |
| Daily missed revenue (fallback calls × avg estimate) | Minimize | Alert on > $5k/day |

---

## Next: [09_Security_Compliance.Plan.md](./09_Security_Compliance.Plan.md)
