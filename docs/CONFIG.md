# Configuration reference

One file: `config/superagent.yaml` in this repo before install;
`$HERMES_HOME/superagent/superagent.yaml` after. Validate any time with:

```bash
python3 scripts/validate_config.py config/superagent.yaml
```

Empty `base_url` / `model` fields are warnings, not errors — the plumbing
can be checked before models are chosen.

## providers

A map of named providers. Each role references one by name.

| Field | Meaning |
|---|---|
| `type` | `openai-compatible` or `anthropic` — both endpoint shapes are wired up |
| `base_url` | Endpoint root, e.g. `https://api.deepseek.com`, `https://api.openai.com/v1`, `https://api.anthropic.com`, or your own gateway |
| `api_key_env` | Name of the environment variable holding the key. **Keys never go in this file.** |

## router / workers

| Field | Meaning |
|---|---|
| `profile` | Hermes profile name to create (must be unique) |
| `provider` | Key into `providers` |
| `model` | Model id at that provider — entirely your choice |
| `toolsets` (workers) | Hermes toolsets granted to the worker |
| `max_concurrent` (workers) | Concurrent tasks per worker |

The Router's toolsets are **not** configurable on purpose: it always gets
`[kanban]` only. A router that can execute will eventually execute.

## watchdog

| Field | Default | Meaning |
|---|---|---|
| `enabled` | true | Master switch |
| `interval_minutes` | 10 | Suggested cron interval |
| `authority` | `report-only` | `report-only` (surface findings only) · `nudge` (comment on the card) · `requeue` (block + reassign) |
| `stall_minutes` | 30 | Running task with no board update for this long = `no_progress` |
| `heartbeat_stale_minutes` | 15 | Worker heartbeat older than this = `heartbeat_stale` |

Scheduling: run `hermes superagent watchdog` from cron, or create a
Hermes cron job that invokes it on the interval above. (Cron registration
is deliberately not automated by the installer yet — Hermes' cron CLI
surface differs across versions; see ASSUMPTIONS.md.)

## events

| Field | Meaning |
|---|---|
| `speculative_execution` | bool, default false — start likely work before being asked |
| `fastpath` | list of `{pattern (regex), action}`; actions: `passthrough`, `drop`, `slowpath`. First match wins; unmatched = slowpath |

## limits

| Field | Meaning |
|---|---|
| `max_workers` | Cap on simultaneously running worker profiles |
| `router_reply_max_words` | Soft budget for the Router's chat replies (detail belongs in files) |
