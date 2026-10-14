# Nexora AI Security — v0.5 Pilot

Do not expose DEMO mode to public customers. LIVE/production startup validates critical configuration.

## Implemented in v0.5

### Browser and authentication
- signed session cookies with configured expiration,
- HTTPS-only cookies in production,
- CSRF tokens on authenticated state-changing requests,
- login-attempt throttling,
- restrictive CSP, frame, referrer and content-type headers,
- generic customer-facing error page.

### Tenant isolation
Business records are scoped to the authenticated workspace. Automated tests verify that one workspace cannot fetch another workspace's lead by object ID.

### Secrets and connectors
Provider secrets are stored in `connector_secrets` and encrypted with `CONNECTOR_ENCRYPTION_KEY`. Connector responses never expose secret values.

Google OAuth state is bound to the signed user session/workspace. HubSpot and webhook credentials are encrypted before storage. Disconnect removes stored connector credentials.

D3Terminal managed-server output redacts common bearer token, API-key, token, secret and password patterns before display.

### Automation control
Human takeover cancels pending follow-up. Booking, completion, loss and explicit customer opt-out stop pending follow-up jobs.

### Production startup
Production rejects:
- `DEMO_MODE=true`,
- the default or short `APP_SECRET`,
- missing `CONNECTOR_ENCRYPTION_KEY`,
- missing initial owner credentials.

## Still required before broad public / enterprise launch

- MFA/passkeys,
- password reset and verified-email workflow,
- expanded RBAC and session/device management,
- managed KMS/HSM secret storage and provider-side OAuth revocation,
- PostgreSQL row-level-security evaluation,
- durable external queue/worker,
- centralized structured logs/metrics/alerting,
- automated dependency/SAST/container/secret scanning,
- backup/restore drills,
- channel-specific legal/consent controls before SMS/voice,
- formal vulnerability-reporting channel.

High-impact actions such as refunds, payment changes, permission changes, destructive operations and real-world dispatch should continue to require policy/approval controls.
