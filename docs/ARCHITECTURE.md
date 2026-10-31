# Architecture: the Super-agent design on Hermes

Source design: DeepSeek Harness team, 《Super-agent 设计探索：迈向更自主的
Agent 系统》 (Oct 2026) — a design exploration, not a product spec. This
document maps its five modules onto Hermes mechanisms and states plainly
where the mapping is complete, partial, or deferred.

| # | Design module | Hermes mapping | Status |
|---|---|---|---|
| 1 | Two-layer architecture (Router / Worker) | Router profile (kanban toolset only, no execution tools) + named worker profiles; Kanban board (SQLite, durable) as the handoff; dispatcher spawns workers as separate processes | Implemented (skeleton) |
| 2 | Event-driven triggers | Hermes gateway already ingests platform messages and webhooks (with route coalescing). This suite adds: a deterministic **Gate** (allowed lists per source; strength explicit/inferred) in front of the Router's judgement, Fast Path rules (plugin `fastpath.py`) that let pattern-matched events skip the Router's LLM judgement, and thread→task passthrough conventions in the Router skill | Gate + Fast Path logic implemented; gateway wiring is phase 2 |
| 3 | Human-facing async interaction | Kanban is fire-and-forget by design (creating a card ends the Router's obligation); results return through gateway channels. Router skill enforces low-noise chat reporting; detail goes to files/board comments | Skill + norms implemented; per-channel tuning is phase 3 |
| 4 | Compute / state / environment separation | State already lives outside sessions (kanban.db, per-profile files) and workers are separate OS processes. Execution can be pushed to Hermes' container/remote terminal backends per profile. Moving the agent *loop* itself into stateless cloud containers is a Hermes-core change, out of scope for a plugin | Partial — execution offload only |
| 5 | Watchdog | Independent checker over the board + activity log. Workers report through a structured enum (`SA-REPORT:`), task stages are derived from those reports (person/working/idle), and stall detection (`watchdog_logic.py`) remains as the fallback for tasks that never report. Runs via `hermes superagent watchdog`, schedulable with Hermes cron. Default authority is report-only; nudge/requeue are config opt-ins | Logic implemented; cron scheduling is manual (see CONFIG.md) |

## Data flow

```
human ──> Router profile ──kanban_create──> kanban.db <──dispatcher──> Worker profiles
              │                                  ▲                          │
              └── reports (chat)                 └── kanban_complete/block ─┘
Watchdog ──reads──> kanban.db + activity.jsonl ──report──> human (report-only default)
```

## Principles carried over from the design

- **Continuous**: profiles and the board persist across sessions and
  restarts; no task lives only inside one conversation.
- **The Router is a bottleneck by design — so batch and bypass it**:
  Fast Path and thread passthrough exist so routine events don't queue
  behind the Router's judgement.
- **Unasked work is opt-in**: the accept mode defaults to `observe`
  (proactive candidates are recorded, never executed) until the
  operator switches the policy to `auto`.

## v0.2: what was adapted from DeepSeek's prototype

DeepSeek published their own implementation
([dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype),
for DeepSeek Harness) alongside the article. Four of its mechanisms are
adapted here, translated from DSH sessions to Hermes profiles + Kanban:

- **Gate + Mandate**: their two-layer Eval (deterministic gate, then
  model assessment) becomes our Gate in front of the Router; their
  immutable Mandate becomes the fixed header block of every card.
- **Accept modes**: their `observe` default — proactive work is
  recorded, not executed — replaces our boolean speculative switch.
- **Report taxonomy + stage table**: worker state is an enum, stages
  are derived from facts; the Watchdog reasons over reports first.
- **Outbox discipline**: store-first delivery with per-conversation
  ordering (`plugin/superagent/outbox.py`), ready for the phase-2
  channel wiring.

Not adapted: their domain engine and SQLite state machine (Hermes'
Kanban board is our state layer), their single-repository worktree
executor (coding-specific; this suite dispatches general work), and
their web panel (Hermes surfaces are the CLI and gateway channels).
