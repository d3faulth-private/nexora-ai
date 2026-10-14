# Nexora AI

> **Your AI Workforce. Always On.**

Nexora AI is an AI workforce operating system for service businesses. It gives a business owner one control center for specialized AI agents that can capture leads, qualify inquiries, prepare follow-ups, support customers, coordinate operations, and surface sensitive actions for human approval.

## Nexora v0.3 branch

This repository contains a testable advanced MVP with:

- **Nexora Manager** — orchestrates objectives across agents
- **Nexora Receptionist** — captures and routes inbound inquiries
- **Nexora Sales** — qualifies leads and proposes appointments
- **Nexora Follow-Up** — re-engages open opportunities
- **Nexora Support** — handles support intake and escalations
- **Nexora Operations** — summarizes activity, tasks, pipeline, and approvals
- Multi-workspace data model
- User login and signed session cookies
- Lead CRM
- Conversation history
- Appointments
- Task management
- Knowledge base
- Connector registry
- Human approval queue
- Agent autonomy levels: manual, guarded, autonomous
- Audit trail
- AI usage tracking
- Pluggable local or OpenAI-compatible model endpoint
- HVAC onboarding profile with services, service area, hours, emergency policy and follow-up rules\n- Human takeover / return-to-AI per conversation\n- Durable scheduled follow-up jobs\n- Google OAuth connector for Gmail + Calendar\n- HubSpot CRM connector\n- Signed outbound webhooks\n- Encrypted connector credential vault\n- External lead intake API\n- Safe mock connector mode for local testing
- SQLite local development
- PostgreSQL Docker deployment
- FastAPI/OpenAPI docs
- Automated tests and GitHub Actions CI

## Quick start

Requires Python 3.11+.

```bash
git clone https://github.com/d3faulth-private/nexora-ai.git
cd nexora-ai
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
uvicorn app.main:app --reload
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

Open:

- Dashboard: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

### Demo login

The default development environment seeds:

- Email: `admin@nexora.local`
- Password: `nexora-demo`

Change these values in `.env` before sharing a deployment.

## Demo workflow

1. Sign in.
2. Open **Avery Johnson**.
3. Send: `My AC stopped cooling and I need someone tomorrow.`
4. Nexora Sales should qualify the lead and propose an appointment.
5. Tell Nexora Manager: `Follow up with everyone who hasn't booked.`
6. Click **Create demo approval** to see a sensitive action enter the human approval queue.
7. Approve or reject it and inspect the audit trail.

## Optional local / OpenAI-compatible model

Nexora works in deterministic local mode without any paid AI API.

To connect an OpenAI-compatible endpoint:

```env
AI_PROVIDER=openai_compatible
AI_BASE_URL=http://localhost:11434/v1
AI_API_KEY=local
AI_MODEL=your-model-name
```

This can point at a compatible local server or a hosted provider. The application falls back to deterministic behavior if the model endpoint is unavailable.

## Docker

```bash
docker compose up --build
```

Then open http://localhost:8000.

## Tests

```bash
pytest
```

## Repository layout

```text
app/
  agents.py       agent routing and business behavior
  ai.py           pluggable AI providers
  config.py       environment configuration
  connectors.py   connector abstraction / safe mock adapters
  db.py           SQLAlchemy database setup
  main.py         web app and API
  models.py       multi-workspace data model
  policy.py       human-approval policy engine
  security.py     password hashing
  seed.py         local demo workspace
  services.py     orchestration/service layer
  static/         dashboard frontend
  templates/      login + control center
docs/
  ARCHITECTURE.md
  SECURITY.md
  ROADMAP.md
tests/
  test_app.py
```

## Important production boundary

This is an advanced MVP intended for product validation and controlled testing. Before using it for real customers, complete the production checklist in `docs/SECURITY.md`, including provider OAuth, encrypted secret storage, tenant isolation review, CSRF protection, rate limiting, background jobs, backups, monitoring, real consent controls, and connector-specific retry/idempotency behavior.

## License / use

No open-source license has been granted in this repository. All rights are reserved unless the repository owner explicitly adds a license.


## v0.3 real connector setup

Generate an encryption key before saving real OAuth or API credentials:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put the result in `.env` as `CONNECTOR_ENCRYPTION_KEY`.

For Google Gmail + Calendar, create a Google OAuth Web Application and configure:

```env
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/connectors/google/callback
```

The dashboard can then start the Google OAuth flow. OAuth tokens are encrypted before being stored in the Nexora database.

HubSpot can be connected with a private-app credential through the dashboard. Outbound webhooks can be configured with an endpoint and signing secret. Nexora signs webhook bodies with `X-Nexora-Signature: sha256=<digest>`.

To enable external lead intake, set a strong `INTAKE_API_KEY`. Clients call:

```text
POST /api/intake/{workspace_id}
X-Nexora-Intake-Key: <key>
```

## Human takeover

Open a lead and choose **Take over**. Nexora stops automated replies for that conversation and records owner replies as human messages. **Return to Nexora** restores AI control.

## Background automation

When an open lead is contacted or qualified, Nexora schedules a durable follow-up job using the delay and retry limits from the HVAC business profile. The background scheduler processes due jobs even when the dashboard is not open.
