# D3FAULTH Operator Terminal

The D3FAULTH terminal is the internal operator console for Nexora. Customers continue to see Nexora branding.

```text
d3faulth@nexora [DEVE]:~$
```

The prompt uses native `prompt-toolkit` styling rather than raw ANSI strings. DEVE, TEST and PROD have distinct environment styles. `NO_COLOR=1` returns plain text.

## Commands

- `status` — runtime, server health/PID, database, agents and jobs
- `doctor` — HEALTHY / NOT CONFIGURED / DISCONNECTED / DEGRADED / FAILED diagnostic
- `revenue` — commercial attribution snapshot
- `opportunities` — prioritized revenue opportunities
- `leads`, `agents`, `jobs`, `connectors` — operational state
- `why last` — explain the latest recorded problem
- `logs --tail N` — tail captured managed-server logs
- `debug last` — latest managed-server failure/log tail
- `serve` — start Uvicorn and wait for healthy `/health`
- `stop`, `restart`, `open` — lifecycle controls
- `history` — redacted command history
- `exit`, `quit`, `q`, Ctrl+D — graceful shutdown

Ctrl+C cancels current input/operation where practical.

Managed-server logs redact common bearer token, API-key, token, secret and password patterns before display.
