# Nexora AI Architecture

## Product model

Nexora is an AI workforce operating layer for service businesses. One workspace represents one business and owns its users, agents, leads, conversations, appointments, automation jobs, approvals, knowledge, connectors, revenue events, and audit activity.

## Runtime

```text
Business Owner
     |
     v
Nexora Manager
     |
     +-------------+-------------+-------------+
     |             |             |             |
Receptionist     Sales       Follow-Up       Support
     |             |             |             |
     +-------------+------+------+-------------+
                          |
                     Operations
                          |
                 Policy / Approval
                          |
             Connector + Action Layer
              /        |        \
          Google    HubSpot    Webhook
                          |
                    SQL Database

Revenue + Opportunity Engine observes the same workspace state.
D3Terminal provides the D3FAULTH operator surface.
```

## Code boundaries

### Web/API
- `app/main.py` — application lifecycle, session auth, core REST routes
- `app/api/routes.py` — commercial/onboarding/connector/revenue routes
- `app/templates/` and `app/static/` — Nexora customer-facing UI

### Workforce
- `app/agents.py` — routing and deterministic agent behavior
- `app/ai.py` — optional OpenAI-compatible model provider
- `app/services.py` — workspace orchestration and dashboard aggregation

### Automation
- `app/automation.py` — durable database-backed follow-up jobs and scheduler

### Integrations
- `app/connectors/providers.py` — Google, HubSpot, and signed webhook adapters
- `app/vault.py` — encrypted credential storage

### Commercial intelligence
- `app/revenue.py` — booked/completed/recovered revenue attribution and opportunity ranking

### Control
- `app/policy.py` — action permission and human approval rules
- `app/security.py` — password primitives
- `d3terminal/` — D3FAULTH operator console, diagnostics, server lifecycle, graceful exit

### Data
- `app/models.py` — workspace-scoped SQLAlchemy schema
- `app/db.py` — SQLite/PostgreSQL engine/session configuration

## Autonomy

Agents support `manual`, `guarded`, and `autonomous` modes. The policy layer remains authoritative: globally sensitive actions can still require explicit approval even when an agent is configured as autonomous.

## Commercial measurement

Nexora separates:

- open pipeline,
- booked pipeline,
- completed revenue,
- recovered revenue,
- open opportunity value.

This is deliberate. Pipeline must never be presented as confirmed revenue.

## Production evolution

The commercial branch deliberately avoids premature platform complexity. Before broader scale, the highest-value architecture work is:

1. production queue/worker instead of an in-process scheduler,
2. Google free/busy scheduling and threaded Gmail replies,
3. strong tenant-isolation tests and RBAC,
4. managed secrets/KMS and OAuth revocation,
5. structured knowledge retrieval,
6. consent-aware SMS/voice,
7. observability and billing.
