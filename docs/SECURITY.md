# Nexora AI Security Notes

Nexora currently targets local product validation. Do not expose the default demo configuration directly to the public internet.

## Before production

### Authentication

- replace demo credentials
- use a strong random `APP_SECRET`
- add CSRF protection
- add login rate limiting and account lockout policy
- consider passkeys / MFA
- add password reset and secure email verification
- add session expiration and device/session management

### Tenant isolation

- review every workspace-scoped query
- add automated cross-tenant isolation tests
- consider PostgreSQL row-level security
- prevent object-ID enumeration between workspaces

### Secrets

Never store provider tokens in plaintext connector records.

Production connectors should use:

- encrypted secret storage
- envelope encryption / managed KMS
- scoped OAuth tokens
- rotation support
- revocation support
- audit logs without leaking credentials

### External actions

Human approval should remain required for high-impact actions such as:

- refunds
- payment/billing changes
- account permission changes
- bulk outreach
- destructive data operations
- technician dispatch or comparable real-world commitments

### Messaging compliance

Before enabling live email/SMS/voice campaigns, implement the consent and opt-out requirements that apply to the business, channel, jurisdiction, and provider.

### Infrastructure

Add:

- HTTPS-only cookies
- trusted host configuration
- secure reverse proxy
- database backups
- migration tooling
- structured logs
- metrics and alerting
- dependency scanning
- secret scanning
- SAST
- container image scanning
- production health/readiness checks

## Reporting

Until a dedicated security email or policy is added, do not publish real production secrets or customer data in GitHub issues.


## v0.3 connector security

Real connector secrets are stored in `connector_secrets` encrypted with a Fernet key derived from `CONNECTOR_ENCRYPTION_KEY`. The key itself must never be committed to the repository.

Google OAuth state is stored in the signed user session and verified on callback. HubSpot credentials and outbound webhook signing secrets are encrypted before database storage.

Before a public deployment:
- move encryption keys to a managed secret/KMS system
- add OAuth disconnect and token-revocation flows
- add CSRF tokens to state-changing browser forms
- make intake credentials unique per workspace
- replace the in-process scheduler with a durable worker/queue
