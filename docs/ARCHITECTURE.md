# Nexora AI Architecture — v0.5 Pilot

## Product boundary

One Nexora workspace represents one HVAC business. Workspace-scoped state includes users, agents, leads, conversations, appointments, follow-up jobs, approvals, knowledge, connectors, revenue events and audit activity.

```text
Lead / Gmail / Intake
        |
        v
Nexora Manager
        |
Receptionist -- Sales -- Follow-Up -- Support
        |                         |
        +-------- Operations -----+
                    |
             Policy / Approval
                    |
 Google Gmail + Calendar / HubSpot / Signed Webhook
                    |
        SQLAlchemy + Alembic database
                    |
 Revenue + Opportunity Engine
```

The D3FAULTH terminal is an internal operator surface; customers see Nexora branding.

## Runtime boundaries

- `app/main.py` — lifecycle, session auth, CSRF enforcement, core routes, security headers and customer error handling
- `app/api/routes.py` — onboarding, connectors, Gmail sync, availability, handoff, revenue and external intake
- `app/services.py` — business orchestration, customer context, dashboard and handoff lifecycle
- `app/automation.py` — database-backed follow-up sequence and scheduler
- `app/connectors/providers.py` — Google, HubSpot and webhook adapters
- `app/revenue.py` — pipeline/revenue attribution and opportunity ranking
- `app/vault.py` — encrypted connector-secret storage
- `migrations/` — Alembic schema history
- `d3terminal/` — diagnostics, prompt theme, managed server logs/health and graceful shutdown

## Lead lifecycle

```text
NEW -> CONTACTED -> QUALIFIED -> BOOKED -> COMPLETED
                              \-> LOST
```

Booking, completion, loss/opt-out and human takeover stop automated follow-up. Returning control to Nexora can resume follow-up for an eligible open lead.

## Scheduling

When Google is connected, Nexora reads primary-calendar free/busy and generates candidate service windows in the workspace timezone. Confirmed bookings create Calendar events. Without a verified Google connection, a proposal remains explicitly unverified.

## Email

Gmail ingestion stores provider events idempotently. Replies to incoming Gmail messages stay in the Gmail thread. Human replies reuse the latest known Gmail thread for the customer where available.

## Security model

Authenticated writes require a session CSRF token. Sessions expire, production cookies are HTTPS-only, login attempts are throttled and browser responses receive restrictive security headers.

Connector credentials are stored separately from connector metadata and encrypted. Production startup rejects demo mode, weak application secrets and missing encryption/bootstrap credentials.

## Database evolution

Alembic owns schema history from v0.5 onward. The baseline uses SQLAlchemy metadata with `checkfirst=True`, allowing both fresh databases and existing v0.4 databases to adopt migration tracking without destructive recreation.

## Scale boundary

The pilot keeps the scheduler in-process and uses one application database. A durable worker/queue, managed KMS, MFA/expanded RBAC and horizontally scaled deployment belong after paid-pilot validation.
