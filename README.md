# D3FAULTH // Nexora AI

> **Your AI Workforce. Always On.**

Nexora AI v0.5 Pilot is an always-on AI workforce for revenue and customer operations in independent HVAC businesses. It captures and qualifies leads, follows up, checks Google Calendar availability, books appointments, keeps Gmail conversations threaded, updates HubSpot, supports human takeover, and separates pipeline from confirmed revenue.

## Pilot workflow

```text
lead arrives
  -> Nexora responds / qualifies
  -> Calendar availability is checked when Google is connected
  -> appointment is proposed
  -> follow-up sequence runs only while the lead remains open
  -> owner can take over at any time
  -> booking stops follow-up
  -> completed job records actual revenue
  -> dashboard shows pipeline, completed and recovered revenue separately
```

## Environment and data safety

Nexora's customer UI is HVAC-first and does not expose development/test environment branding. Internally, `DEMO_MODE` seeds a realistic local HVAC operating day so leads, conversations, appointments, approvals, automation, revenue, and activity can be tested together. Production uses a clean workspace with no seeded customers, appointments, or revenue.

For production set `DEMO_MODE=false`, strong bootstrap owner credentials, a strong `APP_SECRET`, and `CONNECTOR_ENCRYPTION_KEY`. Production startup rejects unsafe defaults.

## Install

```bash
git clone https://github.com/d3faulth-private/nexora-ai.git
cd nexora-ai
git checkout v0.5-pilot
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
python scripts/migrate.py
nexora
```

Default local login:

```text
admin@nexora.local
nexora-demo
```

### Local operational dataset

A fresh local workspace starts with 12 realistic HVAC leads, 8 conversations, 4 appointments, 2 completed jobs, 2 pending follow-ups, 1 approval, and a populated activity trail. The baseline revenue state is:

```text
Booked pipeline      $9,250
Completed revenue    $7,800
Recovered revenue    $5,000
Open opportunity    $14,470
```

If local testing changes the dataset, stop the managed server and restore it from D3Terminal:

```text
workspace reset
workspace reset --confirm
```

The reset command is blocked outside local development/test mode and never seeds production customer workspaces.

## D3FAULTH operator console

```text
d3faulth@nexora [DEVE]:~$
```

Useful commands: `status`, `doctor`, `revenue`, `opportunities`, `leads`, `agents`, `jobs`, `connectors`, `workspace reset`, `why last`, `logs --tail 50`, `debug last`, `serve`, `stop`, `restart`, `open`, `history`, and `exit`.

`serve` waits for `/health` before reporting success and captures managed Uvicorn logs for troubleshooting.

## Integrations

Google OAuth provides Gmail + Calendar. Connected Gmail workspaces are polled automatically (default every 60 seconds), while the manual Sync button uses the same intake path. Nexora can ingest unread email, reply in the same Gmail thread, check Calendar free/busy in the business timezone, propose service windows, and create confirmed Calendar events.

HubSpot private app credentials and webhook credentials are encrypted before storage. Lead progress maps to HubSpot lifecycle stages where applicable. Outbound webhooks are HMAC-signed.

## Pilot safeguards

v0.5 includes CSRF protection, login throttling, expiring sessions, secure production cookies, security headers/CSP, safe customer-facing error pages, encrypted connector credentials, OAuth-state verification, workspace-isolation tests, automation stop conditions, secret-safe operator logs, and an Alembic migration baseline.

## Tests

```bash
python -m pytest
python scripts/migrate.py
python -m compileall -q app d3terminal migrations scripts
node --check app/static/app.js
```

## Commercial rule

Nexora never presents estimated pipeline as completed revenue. The dashboard separates open pipeline, booked pipeline, completed revenue, recovered revenue and open opportunity.

## Scope

v0.5 is HVAC-first. SMS, voice, WhatsApp, additional industries, marketplace/white-label features, subscription billing and Nexora Radar are outside this pilot branch.

No open-source license has been granted. All rights are reserved.


## Positioning boundary

v0.5 is an AI workforce for revenue and customer operations. It is not marketed as an AI CEO, autonomous company manager, or replacement for company leadership. High-impact business decisions remain under human authority.
