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
