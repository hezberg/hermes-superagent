# Changelog

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
