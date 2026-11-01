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
| `toolsets` (workers) | The worker's work toolsets for its CLI platform selection (rendered into `platform_toolsets.cli`; the renderer adds `memory` + `skills`, and the Hermes dispatcher force-adds the kanban lifecycle tools to spawned task workers — neither needs listing) |
| `max_concurrent` (workers) | Concurrent tasks per worker |

The Router's toolsets are **not** configurable on purpose: its CLI
platform selection is always `[kanban, memory, skills]` (written as
`platform_toolsets.cli` in its rendered profile — see ASSUMPTIONS.md
item 2 for why it lives there). A router that can execute will
eventually execute.

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

Scheduling: the installer registers a Hermes **no-agent cron job**
(every `interval_minutes`) that runs
`~/.hermes/scripts/superagent-reminder-tick.py`. In no-agent mode the
script's stdout is delivered verbatim to the chosen platform, and a
silent tick delivers nothing. Point the job at your platform once
(`hermes cron edit <id> --deliver feishu`); if registration failed at
install time, the installer prints the exact `hermes cron create`
command to run by hand.

### Reminders for unclosed work

The tick also runs the reminder pass. A task that needs the person —
**blocked**, **stalled**, or **done but unreviewed** — is surfaced
under a ledger (`~/.hermes/superagent/reminders.json`, inspect with
`hermes superagent reminders`): each situation is fingerprinted by
task + state + when it entered that state, announced once, then
re-announced only after a backoff that doubles each time (base
`remind_backoff_base_minutes`, capped at `remind_backoff_cap_minutes`).
A state change re-arms the reminder; closing the task prunes it.

| Field | Default | Meaning |
|---|---|---|
| `remind_blocked_after_minutes` | 0 | Grace before a blocked card is announced |
| `remind_ready_after_minutes` | 240 | Grace before a finished card asks for review |
| `remind_stalled_after_minutes` | 0 | Extra grace on top of stall detection |
| `remind_backoff_base_minutes` | 60 | Wait before the second announcement |
| `remind_backoff_cap_minutes` | 1440 | Longest wait between announcements |

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

## security

| Field | Meaning |
|---|---|
| `allow_private_urls` | bool, default false. Hermes' SSRF guard blocks web/browser fetches to private, loopback, link-local and CGNAT addresses. Turn on only when this machine legitimately needs those destinations (classic case: Clash/mihomo fake-IP DNS, where public names resolve into 198.18.0.0/15 and every fetch is blocked; or LAN/tailnet-hosted endpoints). When true it is rendered into **every** profile — profiles do not inherit the default profile's security settings, so a global `hermes config set` does not reach workers. Hermes' docs call this a deliberate trust boundary: enabling it lets agents fetch arbitrary LAN addresses. When false the section is omitted from rendered profiles, preserving any per-profile choice made by hand. |
