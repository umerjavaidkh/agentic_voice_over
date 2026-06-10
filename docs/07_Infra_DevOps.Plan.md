# 07 — Infrastructure & DevOps Plan

**Cloud:** Azure (100% — Blob Storage, AKS, Postgres, Redis, Service Bus, Key Vault, Monitor)  
**Orchestration:** AKS (Azure Kubernetes Service)  
**IaC:** Terraform  
**CI/CD:** GitHub Actions  
**Free credit:** Azure $200 free account — covers all dev + staging  

---

## 0. Local Dev Environment (Zero Cloud Cost)

Run everything locally with Docker Compose + Azurite (Azure Storage emulator). No Azure charges during development.

```yaml
# docker-compose.dev.yml

services:
  postgres:
    image: pgvector/pgvector:pg16        # pgvector included, no extra install
    environment:
      POSTGRES_DB: voice_agent_dev
      POSTGRES_USER: devuser
      POSTGRES_PASSWORD: devpass
    ports: ["5432:5432"]
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  azurite:
    image: mcr.microsoft.com/azure-storage/azurite   # Azure Blob Storage emulator
    ports:
      - "10000:10000"   # Blob service
      - "10001:10001"   # Queue service
      - "10002:10002"   # Table service
    volumes:
      - azurite_data:/data
    command: azurite --blobHost 0.0.0.0 --queueHost 0.0.0.0 --tableHost 0.0.0.0

  voice-gateway:
    build: ./services/voice-gateway
    ports: ["8000:8000"]
    env_file: .env.dev
    depends_on: [redis, azurite]

  agent-brain:
    build: ./services/agent-brain
    ports: ["8001:8001"]
    env_file: .env.dev
    depends_on: [postgres, redis]

  pricing-service:
    build: ./services/pricing-service
    ports: ["8002:8002"]
    env_file: .env.dev
    depends_on: [postgres]

  dispatch-adapter:
    build: ./services/dispatch-adapter
    ports: ["8003:8003"]
    env_file: .env.dev

  notification-service:
    build: ./services/notification-service
    ports: ["8004:8004"]
    env_file: .env.dev

volumes:
  postgres_data:
  azurite_data:
```

```bash
# .env.dev — local values only, never commit real keys
AZURE_STORAGE_CONNECTION_STRING="UseDevelopmentStorage=true"  # points to Azurite
POSTGRES_DSN="postgresql://devuser:devpass@localhost:5432/voice_agent_dev"
REDIS_URL="redis://localhost:6379"
OPENAI_API_KEY="sk-..."
DEEPGRAM_API_KEY="..."
ELEVENLABS_API_KEY="..."
TWILIO_ACCOUNT_SID="AC..."
TWILIO_AUTH_TOKEN="..."
LANGSMITH_API_KEY="..."
```

> **Azurite note:** `UseDevelopmentStorage=true` is the connection string that makes the Azure SDK point to the local Azurite emulator instead of real Azure. All `BlobServiceClient` code works identically — swap to a real connection string for staging/prod without any code changes.

```bash
# Start everything
docker compose -f docker-compose.dev.yml up

# Create containers in Azurite on first run
az storage container create --name recordings --connection-string "UseDevelopmentStorage=true"
az storage container create --name transcripts --connection-string "UseDevelopmentStorage=true"
az storage container create --name agent-events --connection-string "UseDevelopmentStorage=true"
```



```
AKS Cluster
├── Namespace: voice-agent-prod
│   ├── Deployment: voice-gateway        (2–10 pods, HPA on concurrent calls)
│   ├── Deployment: agent-brain          (3–15 pods, HPA on CPU + queue depth)
│   ├── Deployment: pricing-service      (2–5 pods, HPA on CPU)
│   ├── Deployment: dispatch-adapter     (2–5 pods)
│   ├── Deployment: notification-service (1–3 pods)
│   ├── StatefulSet: redis               (Azure Cache for Redis, managed)
│   └── Service: postgres                (Azure Database for PostgreSQL Flexible)
│
├── Namespace: voice-agent-staging
│   └── (mirror of prod, lower resource limits)
│
└── Namespace: monitoring
    ├── Deployment: prometheus
    ├── Deployment: grafana
    └── Deployment: langsmith-collector  (optional self-hosted)
```

---

## 2. Kubernetes Manifests

### 2.1 voice-gateway Deployment

```yaml
# infra/k8s/voice-gateway/deployment.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: voice-gateway
  namespace: voice-agent-prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: voice-gateway
  template:
    metadata:
      labels:
        app: voice-gateway
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
    spec:
      containers:
      - name: voice-gateway
        image: acr.azurecr.io/voice-gateway:latest
        ports:
        - containerPort: 8000
        env:
        - name: TWILIO_ACCOUNT_SID
          valueFrom:
            secretKeyRef:
              name: voice-gateway-secrets
              key: twilio_account_sid
        - name: DEEPGRAM_API_KEY
          valueFrom:
            secretKeyRef:
              name: voice-gateway-secrets
              key: deepgram_api_key
        - name: ELEVENLABS_API_KEY
          valueFrom:
            secretKeyRef:
              name: voice-gateway-secrets
              key: elevenlabs_api_key
        - name: LIVEKIT_URL
          value: "wss://livekit.yourdomain.com"
        - name: AGENT_BRAIN_WS_URL
          value: "ws://agent-brain-service:8001/ws"
        resources:
          requests:
            cpu: "500m"
            memory: "512Mi"
          limits:
            cpu: "2000m"
            memory: "2Gi"
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
```

### 2.2 HPA for voice-gateway

```yaml
# infra/k8s/voice-gateway/hpa.yaml

apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: voice-gateway-hpa
  namespace: voice-agent-prod
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: voice-gateway
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
  - type: Pods
    pods:
      metric:
        name: active_calls_count          # custom metric from Prometheus
      target:
        type: AverageValue
        averageValue: "5"                 # scale up when avg pod handles >5 calls
```

### 2.3 agent-brain Deployment

```yaml
# infra/k8s/agent-brain/deployment.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-brain
  namespace: voice-agent-prod
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: agent-brain
        image: acr.azurecr.io/agent-brain:latest
        ports:
        - containerPort: 8001
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: agent-brain-secrets
              key: openai_api_key
        - name: LANGSMITH_API_KEY
          valueFrom:
            secretKeyRef:
              name: agent-brain-secrets
              key: langsmith_api_key
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: agent-brain-secrets
              key: redis_url
        - name: POSTGRES_DSN
          valueFrom:
            secretKeyRef:
              name: agent-brain-secrets
              key: postgres_dsn
        resources:
          requests:
            cpu: "1000m"
            memory: "1Gi"
          limits:
            cpu: "4000m"
            memory: "4Gi"
```

---

## 3. Dockerfiles

### voice-gateway

```dockerfile
# services/voice-gateway/Dockerfile

FROM python:3.12-slim

WORKDIR /app

# System deps for audio processing
RUN apt-get update && apt-get install -y \
    libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user
RUN useradd -m -u 1001 appuser && chown -R appuser /app
USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--loop", "uvloop"]
```

### agent-brain

```dockerfile
# services/agent-brain/Dockerfile

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared models too
COPY ../../shared /app/shared
COPY . .

RUN useradd -m -u 1001 appuser && chown -R appuser /app
USER appuser

# Uvicorn with WebSocket support
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", \
     "--workers", "2", "--loop", "uvloop", "--ws", "websockets"]
```

---

## 4. Terraform — Azure Resources

```hcl
# infra/terraform/main.tf

resource "azurerm_kubernetes_cluster" "aks" {
  name                = "voice-agent-aks"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  dns_prefix          = "voice-agent"
  kubernetes_version  = "1.29"

  default_node_pool {
    name            = "system"
    node_count      = 3
    vm_size         = "Standard_D4s_v5"   # 4 vCPU, 16GB RAM
    os_disk_size_gb = 50
    enable_auto_scaling = true
    min_count       = 3
    max_count       = 20
  }

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_postgresql_flexible_server" "postgres" {
  name                = "voice-agent-pg"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  version             = "16"
  sku_name            = "GP_Standard_D4s_v3"   # 4 vCPU, 16GB
  storage_mb          = 65536
  backup_retention_days = 30
  administrator_login    = var.pg_admin_user
  administrator_password = var.pg_admin_password
}

resource "azurerm_redis_cache" "redis" {
  name                = "voice-agent-redis"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  capacity            = 2
  family              = "C"
  sku_name            = "Standard"             # 6GB, with replica
  enable_non_ssl_port = false
  minimum_tls_version = "1.2"
}

resource "azurerm_service_bus_namespace" "sb" {
  name                = "voice-agent-sb"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "Standard"
}

resource "azurerm_service_bus_queue" "failed_dispatch" {
  name                = "failed-dispatch"
  namespace_id        = azurerm_service_bus_namespace.sb.id
  lock_duration       = "PT1M"
  max_delivery_count  = 10
}

resource "azurerm_container_registry" "acr" {
  name                = "voiceagentacr"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  sku                 = "Standard"
  admin_enabled       = false
}

resource "azurerm_key_vault" "kv" {
  name                = "voice-agent-kv"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"
  soft_delete_retention_days = 90
}

# Azure Blob Storage — replaces AWS S3 entirely
resource "azurerm_storage_account" "main" {
  name                     = "voiceagentstore${var.env}"   # e.g. voiceagentstoreprod
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"              # dev/staging: LRS
  # account_replication_type = "ZRS"            # prod: zone-redundant
  min_tls_version          = "TLS1_2"

  blob_properties {
    delete_retention_policy {
      days = 7                                   # soft-delete safety net
    }
  }
}

resource "azurerm_storage_container" "recordings" {
  name                  = "recordings"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "transcripts" {
  name                  = "transcripts"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "agent_events" {
  name                  = "agent-events"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

resource "azurerm_storage_management_policy" "lifecycle" {
  storage_account_id = azurerm_storage_account.main.id

  rule {
    name    = "delete-recordings-90d"
    enabled = true
    filters {
      prefix_match = ["recordings/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = 90
      }
    }
  }

  rule {
    name    = "delete-transcripts-365d"
    enabled = true
    filters {
      prefix_match = ["transcripts/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = 365
      }
    }
  }
}

# Budget alert — protect the $200 free credit
resource "azurerm_consumption_budget_resource_group" "budget" {
  name              = "voice-agent-budget-alert"
  resource_group_id = azurerm_resource_group.rg.id
  amount            = 150
  time_grain        = "Monthly"

  time_period {
    start_date = "2024-01-01T00:00:00Z"
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    contact_emails = [var.alert_email]
  }
}
```

---

## 5. CI/CD — GitHub Actions

```yaml
# .github/workflows/deploy.yml

name: Build & Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - name: Install dependencies
      run: pip install -r requirements-dev.txt
    - name: Run tests
      run: pytest tests/ -v --cov=services --cov-report=xml
    - name: Upload coverage
      uses: codecov/codecov-action@v4

  build-and-push:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    strategy:
      matrix:
        service: [voice-gateway, agent-brain, pricing-service, dispatch-adapter]
    steps:
    - uses: actions/checkout@v4
    - name: Login to ACR
      uses: azure/docker-login@v1
      with:
        login-server: voiceagentacr.azurecr.io
        username: ${{ secrets.ACR_USERNAME }}
        password: ${{ secrets.ACR_PASSWORD }}
    - name: Build and push
      run: |
        IMAGE=voiceagentacr.azurecr.io/${{ matrix.service }}:${{ github.sha }}
        docker build -f services/${{ matrix.service }}/Dockerfile -t $IMAGE .
        docker push $IMAGE

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
    - uses: azure/aks-set-context@v3
      with:
        creds: ${{ secrets.AZURE_CREDENTIALS }}
        cluster-name: voice-agent-aks
        resource-group: voice-agent-rg
    - name: Deploy to AKS
      run: |
        for SERVICE in voice-gateway agent-brain pricing-service dispatch-adapter; do
          kubectl set image deployment/$SERVICE \
            $SERVICE=voiceagentacr.azurecr.io/$SERVICE:${{ github.sha }} \
            -n voice-agent-prod
          kubectl rollout status deployment/$SERVICE -n voice-agent-prod
        done
```

---

## 6. Resource Sizing Guide

| Service | Min pods | Max pods | CPU request | Memory request | Notes |
|---------|----------|----------|-------------|----------------|-------|
| voice-gateway | 2 | 10 | 500m | 512Mi | Audio WebSocket = high memory/pod |
| agent-brain | 3 | 15 | 1000m | 1Gi | LangGraph graph + LLM calls |
| pricing-service | 2 | 5 | 250m | 256Mi | Mostly async I/O |
| dispatch-adapter | 2 | 5 | 250m | 256Mi | Mostly HTTP calls |
| notification-service | 1 | 3 | 100m | 128Mi | Fire-and-forget |

**Azure node pool:** `Standard_D4s_v5` (4 vCPU, 16GB RAM) — packs ~8 agent-brain pods per node.

---

## Next: [08_Observability.Plan.md](./08_Observability.Plan.md)
