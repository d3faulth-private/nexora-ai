# D3FAULTH // Nexora AI

> **Your AI Workforce. Always On.**

Nexora AI is an AI workforce platform for service businesses. The first commercial focus is HVAC: respond to leads quickly, qualify them, follow up automatically, book appointments, update connected systems, surface revenue opportunities, and show the owner what Nexora helped generate.

## Commercial build

The `v0.4-commercial` branch adds the first revenue-focused layer on top of the validated v0.3 foundation:

- Nexora Manager plus Receptionist, Sales, Follow-Up, Support, and Operations agents
- HVAC business onboarding
- lead CRM and conversation history
- appointment proposals and booking
- human takeover / return-to-AI
- approval policy for sensitive actions
- durable follow-up jobs
- Google Gmail + Calendar connector
- HubSpot connector
- signed outbound webhooks
- encrypted connector credentials
- external lead intake API
- revenue attribution: booked, completed, and recovered value
- proactive opportunity engine
- D3FAULTH operator terminal
- automated tests and CI

## Start with the D3FAULTH terminal

Requires Python 3.11+.

```powershell
git clone https://github.com/d3faulth-private/nexora-ai.git
cd nexora-ai
git checkout v0.4-commercial

python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env

nexora
```

The console opens as:

```text
D3FAULTH // NEXORA AI
Security Engineering // AI Systems // Operator Console

d3faulth@nexora [DEVE]:~$
```

Useful commands:

```text
status
doctor
revenue
opportunities
leads
agents
jobs
connectors
why last
serve
stop
restart
open
history
exit
```

`exit`, `quit`, `q`, or Ctrl+D use the graceful shutdown path. Ctrl+C cancels the current terminal input/operation where practical instead of treating every interrupt as a hard shutdown.

You can also run the web application directly:

```powershell
uvicorn app.main:app --reload
```

Dashboard: `http://127.0.0.1:8000`  
API docs: `http://127.0.0.1:8000/docs`

Default demo login:

```text
admin@nexora.local
nexora-demo
```

## Revenue workflow

The Stage-1 commercial loop is intentionally simple:

```text
lead arrives
    ↓
instant qualification
    ↓
appointment proposal
    ↓
follow-up if not booked
    ↓
confirmed appointment
    ↓
completed job revenue
    ↓
Nexora attribution + ROI dashboard
```

The opportunity engine ranks open leads by value and state so the owner can immediately see where potential revenue is sitting.

## Real connectors

Generate an encryption key before storing real provider credentials:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set `CONNECTOR_ENCRYPTION_KEY` in `.env`.

Google OAuth:

```env
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/connectors/google/callback
```

HubSpot and webhook credentials can be configured through the dashboard and are encrypted before storage.

## Repository layout

```text
app/
  api/              HTTP API routes
  connectors/       external provider adapters
  static/           dashboard JavaScript/CSS
  templates/        web UI
  agents.py         workforce routing/behavior
  ai.py             model-provider abstraction
  automation.py     scheduled follow-up execution
  models.py         SQLAlchemy data model
  revenue.py        attribution + opportunity engine
  services.py       orchestration layer
  policy.py         approval policy
  security.py       authentication primitives
  vault.py          connector secret encryption

d3terminal/
  branding.py       D3FAULTH terminal identity
  diagnostics.py    system/business diagnostics
  runtime.py        managed local server lifecycle
  shell.py          operator commands and graceful exit

tests/
docs/
scripts/
```

## Tests

```powershell
pytest
python -m compileall -q app d3terminal
node --check app/static/app.js
```

## Product rule

Nexora is not optimized for feature count. Product work is prioritized by whether it helps:

1. acquire a paying customer,
2. generate or recover customer revenue,
3. retain the customer,
4. reduce meaningful operating work, or
5. justify higher pricing.

See `docs/COMMERCIAL_WORKFLOW.md` and `docs/OPERATOR_TERMINAL.md`.

## Production boundary

This branch is a commercial-validation build, not a finished enterprise SaaS. Before public customer deployment, complete the controls in `docs/SECURITY.md`, including CSRF protection, stronger tenant isolation, production secret management, durable external workers, rate limiting, MFA, connector revocation, backups, monitoring, and consent controls.

## License

No open-source license has been granted. All rights are reserved unless the repository owner explicitly adds a license.
