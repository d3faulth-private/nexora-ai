# D3FAULTH Operator Terminal

The D3FAULTH terminal is the internal operator surface for Nexora. Nexora customers continue to see Nexora branding; D3FAULTH identifies the creator/operator environment.

## Prompt

```text
d3faulth@nexora [DEVE]:~$
```

## Core commands

- `status` — runtime, database, agents, and jobs
- `doctor` — diagnostic summary
- `revenue` — commercial attribution snapshot
- `opportunities` — prioritized open revenue opportunities
- `leads` — recent lead state
- `agents` — workforce state/autonomy
- `jobs` — automation queue
- `connectors` — provider state
- `why last` — explain the latest recorded failure/problem
- `serve` — start a local Nexora server managed by this console
- `stop` / `restart` — lifecycle control
- `open` — open the local dashboard
- `history` — current operator session history
- `exit`, `quit`, `q` — graceful shutdown

Natural shortcuts currently map a few common operator intents, including `what's wrong`, `what needs my attention`, `who should i call today`, and `show revenue`.

## Exit behavior

`exit`, `quit`, `q`, and Ctrl+D use one shutdown controller. It stops any web server started by the console, closes operator-owned resources, restores the terminal state, prints a session summary, and returns exit code 0.

Ctrl+C cancels the current input/operation where practical and returns to the D3 prompt.

## Safety

The terminal intentionally redacts session-history entries that appear to contain tokens, secrets, passwords, or inline keys. Production secret values should never be printed by diagnostic commands.
