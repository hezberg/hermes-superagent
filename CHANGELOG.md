# Changelog

## 0.3.0 — 2026-11-01

The last-mile release. Operator direction (docs/PRINCIPLES.md): stop
adding mechanism, start finishing the distance between "works in a
terminal" and "feels like a good assistant". Four chunks, each traced
to a specific rough edge of the first live install:

- **Finished work becomes global memory.** Every terminal card is
  recorded in `~/.hermes/superagent/journal.jsonl` (+ `journal.md`
  for humans): title, assignee, outcome, the native completion
  summary and artifact paths. New `hermes superagent digest` prints
  recent outcomes in prose; `sa_status` carries the last few; the
  Router skill now opens fresh conversations with a one-line
  continuity glance at the journal. (The borrowed design has no such
  layer — its ticket outcomes never become shared memory.)
- **`hermes superagent doctor`.** The whole install checked in plain
  sentences, each finding with its fix attached: key env vars, legacy
  or missing toolset selection, router carrying execution tools,
  fake-IP DNS vs the SSRF guard per profile, curly quotes in rendered
  configs, private model endpoints, board state. Every check is a
  failure the first install actually hit; nobody should need a log
  tail again. The installer also self-checks plugin loading after
  install and explains, in prose, what works without it.
- **The user's config can no longer be eaten by an upgrade.** Once a
  filled-in copy exists under `~/.hermes/superagent/`, the installer
  prefers it over a pristine repo template (scripts/pick_config.py)
  and says so; the closing text names the effective config and where
  future edits belong.
- **The chat entry is prepared.** The Router renders its restricted
  toolset selection for the Feishu platform too; the Router skill
  defines the completion wake-up protocol (verify the handoff, report
  in brief prose, relay a block as one question with a recommended
  answer, never forward board dumps); SETUP.md §6 documents the host
  wiring, with gateway-chat routing flagged as the one
  version-dependent step (ASSUMPTIONS item 10).

91 tests passing; every chunk sandbox-verified, including an upgrade
run that recovered the operator's filled config from the suite path
and a doctor run against a deliberately field-broken install.

## 0.2.2 — 2026-11-01

Lessons from the first live install's completed card, applied:

- **Reporting no longer depends on the worker skill being loaded.**
  The field worker completed its card through Hermes' native handoff
  (kanban_complete summary + artifacts) without ever loading the
  worker skill, so the mandated `SA-REPORT:` comment never appeared.
  The plugin now derives each task's report kind from the board's
  native records first — `derive_report()` in reports.py maps
  run-concluding events (completed → ready, blocked → blocked,
  gave_up/crashed/timed_out → failed) and the task status; a new
  defensive `board_events()` reader feeds it. An explicit SA-REPORT
  comment still wins when present, as an optional upgrade. The worker
  skill is rewritten around the native discipline instead: artifacts
  carry deliverables (scratch workspaces are deleted at completion),
  the completion summary answers the acceptance check point by point,
  `kanban_block` with one concrete question when stuck.
- **`security.allow_private_urls` is now a suite option.** Profiles
  do not inherit the default profile's security settings (verified in
  the field: a global `config set` left workers SSRF-blocked), so
  when the option is true the renderer writes the `security:` section
  into every profile. Default false; the config comments spell out
  the trust boundary and the fake-IP DNS case that needs it.
- ASSUMPTIONS gains item 9, recording the three field findings
  (discretionary skill loading, no cross-profile config inheritance,
  fake-IP DNS vs the SSRF guard) so they are not relearned.

## 0.2.1 — 2026-11-01

Field fix from the first live install: the Router had no kanban tools
at all, and every other tool instead.

- **Toolset selection moved to `platform_toolsets`.** v0.1/v0.2.0
  rendered `agent.toolsets`, which Hermes does not read; profile
  sessions silently fell back to the full default toolset (web
  included) and the deliberately opt-in `kanban` toolset never
  appeared, so the Router did the work itself and the board stayed
  empty. Templates now render `platform_toolsets.cli` — Router:
  `[kanban, memory, skills]`; workers: their work toolsets — and the
  installer additionally runs `hermes -p <router> tools enable kanban`
  through Hermes' own tooling as a second path. Verified against the
  official Kanban docs; ASSUMPTIONS item 2 is now resolved.
- Worker `toolsets` in the config examples no longer list `kanban`
  (the dispatcher force-adds the lifecycle tools to spawned workers
  via `HERMES_KANBAN_TASK`) or `search` (covered by `web`). The
  renderer unions every worker's selection with `memory` + `skills`
  so workers can load their bundled skill.

## 0.2.0 — 2026-10-31

Authorization and reporting layer, adapted from DeepSeek's
dsh-superagent-prototype (see README "Design references").

- **Gate** (`plugin/superagent/gate.py`, pure logic, unit-tested):
  deterministic admission in front of the Router's judgement —
  per-source allowed lists, explicit vs inferred strength, bot-raised
  candidates, stop precedence. Rejected events never reach a model.
- **Mandates**: every accepted task records an immutable Mandate
  (policy version = hash of the policy block, source, sender, strength,
  scope), rendered as the fixed header block of the Kanban card.
- **Accept modes**: `policy.accept_mode` — `observe` (default: inferred
  candidates recorded, never executed) or `auto`. Replaces the
  `events.speculative_execution` boolean, which is still honoured as a
  legacy alias (`true` → `auto`).
- **Structured reports** (`plugin/superagent/reports.py`): workers end
  state-changing turns with `SA-REPORT: progress|waiting|ready|blocked|
  failed|dropped`; task stages (person/working/idle) are derived from
  the latest report. The watchdog CLI prints stages alongside the
  existing timestamp stall detection, which remains as fallback.
- **Outbox** (`plugin/superagent/outbox.py`): store-first message
  delivery with per-(ticket, conversation) ordering and a 3-failure
  problem flag, ready for the phase-2 channel wiring.
- **Worker skill**: bundled `worker-superagent` skill (Mandate scope,
  SA-REPORT discipline, hand-back rules); installed into every worker
  profile alongside the Router skill, which was expanded with the Gate,
  Mandate, subscription and report-reading rules.
- **Config**: new `policy` block (validated), per-role
  `reasoning_effort`, `limits.reserved_human_slot` (one slot always
  kept for a human's follow-up). `hermes superagent status` now shows
  the effective accept mode.
- **SETUP.md**: agent-guided setup — probe first, one question at a
  time, plan before executing, keys only ever entered by the operator
  in their own terminal.

## 0.1.0 — 2026-10-31

Initial CLI skeleton.

- Repository layout and configuration system: one `superagent.yaml`,
  provider abstraction with OpenAI-compatible and Anthropic endpoint
  types wired up, per-role models fully user-configured, keys only via
  environment variables.
- Config validator (`scripts/validate_config.py`) and profile renderer
  (`scripts/render_profiles.py`) with the provider→Hermes mapping
  isolated in one function.
- Hermes plugin skeleton: `/tasks` and `/stop` gateway commands,
  `sa_status` tool, exception-proof activity hooks, `hermes superagent
  status|watchdog` CLI, bundled Router skill.
- Pure decision logic, unit-tested: Fast Path classification and
  Watchdog stall detection (23 unit tests).
- Profile templates: dispatch-only Router (kanban toolset only) and
  general / research / deep workers.
- `install.sh` / `uninstall.sh`: preflight, collision refusal, manifest
  of created paths, verified-clean uninstall. Full install→uninstall
  cycle exercised in a sandbox with a stub Hermes.
- Docs: architecture mapping (including the one module that is only
  partially achievable outside Hermes core), config reference, and an
  assumptions list to verify at first live install.
