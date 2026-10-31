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

Each role also accepts an optional `reasoning_effort` (empty = provider
default), seeded when the profile's session is created.

## policy — the Gate and Mandates

Authorization runs before model judgement (see `plugin/superagent/gate.py`).

| Field | Meaning |
|---|---|
| `accept_mode` | `observe` (inferred candidates are recorded, never executed) · `auto` (rule-matched inferred candidates become real work). Explicit requests from allowed senders are accepted in both modes |
| `sources.<name>.allowed_senders` | Identities allowed to ask for work through that source, **in that source's own terms** (identities are never mapped across sources). Empty = nobody. The `cli` source always allows the local operator |
| `bots` | Bot identities whose activity may raise inferred candidates |
| `rules` | Proactive rules in your own words: `{id, instruction}`. Rules can narrow unasked work, never widen it past the allowed lists |

Every accepted task records a **Mandate**: the policy version (a hash of
this whole block — it changes when the block does), source, sender,
strength (`explicit` / `inferred`) and scope. The Mandate is immutable;
wider scope means a new task. Configs from v0.1 without a `policy` block
keep working: the Gate defaults to `observe`, CLI only, and the old
`events.speculative_execution: true` is honoured as `auto`.

## Worker reports

Workers end state-changing turns with a board comment whose first line
is `SA-REPORT: <kind>` — `progress`, `waiting`, `ready`, `blocked`,
`failed`, `dropped`. The Watchdog and the Router derive each task's
stage from the latest report (delivery failed → `person/delivery`;
attention open → `person/answer`; `ready` → `person/review`;
`blocked`/`failed` → `person/*`; no assignment → `working/queued`;
`waiting` → `idle`; otherwise `working`). Timestamp stall detection
remains as a fallback for tasks that never report.

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
| `fastpath` | list of `{pattern (regex), action}`; actions: `passthrough`, `drop`, `slowpath`. First match wins; unmatched = slowpath. (Proactive behaviour moved to `policy.accept_mode` in v0.2.) |

## limits

| Field | Meaning |
|---|---|
| `max_workers` | Cap on simultaneously running worker profiles |
| `reserved_human_slot` | bool, default true — always keep one slot free for a human's follow-up, so new work cannot starve an existing task's owner |
| `router_reply_max_words` | Soft budget for the Router's chat replies (detail belongs in files) |
