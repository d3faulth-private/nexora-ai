# Nexora AI Architecture

## Product model

Nexora is designed as an AI workforce operating system rather than a generic workflow canvas.

A workspace represents one business. Each workspace owns its users, agents, leads, conversations, appointments, tasks, approvals, knowledge, connectors, activities, and usage.

## Runtime flow

```text
Business Owner
     |
     v
Nexora Manager
     |
     +----------------+----------------+----------------+
     |                |                |                |
Receptionist        Sales          Follow-Up        Support
     |                |                |                |
     +----------------+-------+--------+----------------+
                              |
                        Operations Agent
                              |
                    Policy / Approval Engine
                              |
                Connector + Action Abstraction
                 /         |         |        \
              Email     Calendar     CRM     Webhook
                              |
                         SQL Database
```

## Layers

### 1. Web/API layer

`app/main.py`

FastAPI exposes the dashboard and REST API. Session cookies currently authenticate the local product experience.

### 2. Service/orchestration layer

`app/services.py`

This layer owns workspace-scoped orchestration, lead processing, manager objectives, approvals, activity recording, and dashboard aggregation.

### 3. Agent behavior layer

`app/agents.py`

Agents decide routing and domain behavior. The MVP combines deterministic rules with optional model-assisted response generation.

### 4. AI provider layer

`app/ai.py`

Nexora can run without a model or use an OpenAI-compatible endpoint. Provider responses record usage metadata.

### 5. Policy layer

`app/policy.py`

Sensitive actions such as refunds, bulk outreach, billing changes, data deletion, dispatch, and account permission changes require human approval.

### 6. Connector layer

`app/connectors.py`

Connectors currently run in safe mock mode. Real email/calendar/CRM adapters should implement the same conceptual contract with:

- OAuth or secure service credentials
- encrypted secret storage
- idempotency keys
- retry policy
- provider rate-limit handling
- audit metadata
- clear consent scope

### 7. Data layer

`app/models.py`

The SQLAlchemy schema is workspace-scoped and supports SQLite locally and PostgreSQL in Docker.

## Agent autonomy

Every agent has an autonomy level:

- **manual** — actions require human approval
- **guarded** — routine reversible actions can proceed; sensitive actions require approval
- **autonomous** — broader automation, but globally sensitive actions still require policy approval

The policy engine remains authoritative over an agent's configured autonomy.

## Production evolution

Recommended next architectural additions:

1. Redis-backed background job queue
2. provider-specific OAuth vault
3. row-level tenant isolation tests
4. event bus / durable workflow engine
5. model routing and prompt/version registry
6. semantic knowledge retrieval
7. connector SDK
8. billing / metering subsystem
9. organization roles and fine-grained permissions
10. real-time websocket event stream
