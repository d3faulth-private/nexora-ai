# Nexora v0.5 Pilot Deployment

## Demo validation

```bash
cp .env.example .env
python scripts/migrate.py
nexora
```

Keep `DEMO_MODE=true` for sample HVAC data and optional mock connectors.

## Live pilot

Configure at minimum:

```env
APP_ENV=production
DEMO_MODE=false
APP_SECRET=<32+ character random secret>
CONNECTOR_ENCRYPTION_KEY=<Fernet key>
BOOTSTRAP_BUSINESS_NAME=Customer HVAC Company
BOOTSTRAP_ADMIN_EMAIL=owner@example.com
BOOTSTRAP_ADMIN_PASSWORD=<12+ character unique password>
DATABASE_URL=<production database URL>
GOOGLE_CLIENT_ID=<OAuth client>
GOOGLE_CLIENT_SECRET=<OAuth secret>
GOOGLE_REDIRECT_URI=https://your-domain.example/api/connectors/google/callback
ALLOWED_HOSTS=your-domain.example
GMAIL_POLL_SECONDS=60
```

Generate a connector encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Install, migrate, and start:

```bash
python -m pip install -e .
python scripts/migrate.py
nexora
```

In D3Terminal run `doctor`, then `serve`. Connect Google/HubSpot as needed, finish onboarding, and run one end-to-end test lead before accepting real inquiries.

## TLS and network

Production cookies require HTTPS. Terminate TLS at a trusted reverse proxy and keep the app/database private from unnecessary network exposure.

## Upgrade

Back up the database, deploy code, run `python scripts/migrate.py`, restart, then verify `doctor`, `status`, and `logs --tail 50`.

The v0.5 baseline migration is non-destructive for existing v0.4 tables.

## Rollback

Code rollback does not automatically reverse database changes. The v0.5 baseline downgrade is intentionally non-destructive. Later schema migrations should document their own rollback procedure.
