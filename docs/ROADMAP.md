# Roadmap

Designed and mechanism-verified, deliberately not yet built.
Priority as of 2026-11-02: polish the shipped surface first.
Nothing here starts without a fresh go-ahead.

## 1. Time-awareness for suite profiles

Status: designed 2026-11-02, not implemented. Open decision:
scope — Router only, or Router + Workers (recommendation: both;
Workers judge task timing too, at the same cost).

Design:

- A `pre_llm_call` hook returns `{"context": ...}` carrying ONE
  line, computed in code at call time:
  `[time] 2026-11-02 Mon 00:16 Asia/Shanghai` — date, explicit
  weekday, minute-precision time, timezone name.
- The placement is the whole design. That context slot rides the
  current user turn; it never touches the system prompt. SOUL.md
  and the auto-loaded skill texts form a byte-stable prefix that
  provider prompt caches (DeepSeek's included) match on — a
  clock anywhere in the prefix would invalidate it every minute
  and re-bill the full prefix on every turn. In the user-turn
  slot the cost is ~20 tokens per turn and the prefix hash never
  changes. History turns are immutable once written, so
  incremental history caching is unaffected too.
- The weekday is spelled out because models derive it from the
  date unreliably; ages and durations stay code-rendered (as
  `status` already does), never model-computed.
- Config, in `superagent.yaml`: `time: {enabled: true,
  timezone: local | <IANA name>, precision: minute | hour |
  day}`. The plugin reads the config when the hook fires — no
  re-render, edits apply like every other config edit.
- One static line in each role skill: relative dates ("by
  Friday", "tomorrow") resolve against the turn's `[time]` line.
  Static text lives in the cached prefix; it costs nothing.
- Non-goals: the journal, watchdog and reminder tick are code
  and already run on real clocks.

Acceptance:

- The hook injects exactly once per user turn, including inside
  tool-call loops (verify against Hermes' loop; no stacking).
- Provider cache-hit usage is unchanged with the feature on
  (compare on the operator's gateway, before/after).
- A card created from "by this Friday" lands on the correct
  date.

## 2. Mid-run Router ↔ Worker communication

Status: mechanism verified in Hermes source 2026-11-02;
protocol and surface not yet written.

Finding — the plumbing is native, no new channel is needed:

- A dispatcher-spawned worker is a `hermes -p <profile> chat -q`
  subprocess carrying `HERMES_KANBAN_TASK`. On activity it polls
  its own task for new comments (`tools/kanban_tools.py`:
  `inject_new_comments_from_env` — per-task watermark, ≥6s
  throttle, its own comments skipped) and Hermes steers them
  into the live turn via `agent.steer()`, formatted as an
  operator note delivered mid-run.
- Consequence: a `kanban_comment` written by the Router, the
  operator, or the dashboard reaches a *running* worker at its
  next tool step. No block → comment → unblock dance (that is
  exactly what the mechanism exists to replace). A worker stuck
  inside one long tool call sees the note when that call
  returns. `delegate_task` children are excluded by design.

To build (all thin — protocol and surface, no plumbing):

- Router skill playbook: progress check = `kanban_show` (comments,
  events, heartbeat); asking or steering = comment on the card;
  set expectations — delivery lands at the worker's next tool
  step, it does not interrupt an in-flight tool call.
- Worker skill discipline: progress comments at milestones
  (start, halfway, before a long operation); a mid-run note that
  asks something MUST be answered with a comment — that is the
  only return channel; a scope-changing note outranks the card
  body, and the conflict gets noted in a comment.
- Surface: `status -v` and `/board` show the latest comment on
  each running card (today they show metadata only).

Non-goal: no second channel — no suite-side signal table or
file protocol. The native watermark, dedupe and throttle
already handle delivery; a parallel path would fight it.

Acceptance: dispatch a deliberately long card; from another
surface, comment a progress question onto it; the worker
acknowledges it in its following steps and posts a progress
comment back; the Router's `kanban_show` shows the exchange.
