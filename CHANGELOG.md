## 0.10.2 — 2026-11-01

- **Wizard: a duplicate Feishu app is a hard stop on EVERY path.**
  The paste path already refused duplicates; the bind-through-
  Hermes-setup path only warned and continued (field report: the
  operator deliberately bound the default profile's app to the
  router — the wizard waved it through). Now a conflicting bind
  stops the flow: remove it from the router profile and bind a
  NEW app (loop), remove it and continue without an entry, or
  leave it — in which case the wizard records NO entry, says so
  in the final summary, and exits 1. Credentials are actively
  removed on the first two choices: leaving them on disk would
  let the gateway bring the duplicate binding up anyway.
- **Wizard UI is readable.** Semantic ANSI styling (stdlib only):
  numbered step headers, bold prompts, cyan option numbers with
  the default marked in green, errors as bold-red ✗ lines,
  warnings in yellow, successes as green ✓. Color disables
  itself off-TTY and under NO_COLOR
  (SUPERAGENT_WIZARD_COLOR=always|never overrides).

## 0.10.1 — 2026-11-01

- **Wizard: a menu selection that names its model is final.**
  Picking a provider whose Hermes entry already defines a model
  (the menu line shows it) no longer triggers a redundant
  "Model for ..." prompt with a blank default — the choice settles
  provider and model together. The default profile's own block is
  no longer listed as a pseudo-selection either; "inherit" covers
  it. Models are asked only for entries that define none.
- Wizard now checks each CHOSEN provider's key variable at
  selection time and warns on the spot when it has no value,
  instead of letting the install fail its first request later.

## 0.10.0 — 2026-11-01

- **Interactive setup wizard** (`hermes superagent setup`, or
  `install.py --wizard`): the guided front door the installer
  always lacked. Preflight refuses to proceed until Hermes itself
  is ready — no default model means "run `hermes setup` first",
  and a default model whose key variable has no value is a hard
  stop (that combination passes naive checks and fails only at
  the first real request). Then, in order: worker topology (one
  worker / all three / pick), a provider+model choice per role
  from the Hermes menu, an optional Feishu entry — paste a NEW
  dedicated app's App ID + Secret (the ID is checked against every
  profile: a duplicate is a hard stop explaining that one app
  serves one profile; or bind through Hermes' own per-profile
  setup, QR included) — credentials written to the router
  profile's .env BEFORE install so postflight passes in one run.
  Finishes with `hermes kanban init`, reminder-delivery setup,
  a doctor verdict, and an optional gateway restart. Re-running
  the wizard reconfigures in place, with current choices as
  defaults. The whole flow is covered by scripted-input tests,
  including the duplicate-App-ID stop.

## 0.9.0 — 2026-11-01

The native-mechanisms release: a source-level survey of Hermes
(docs/research/HERMES-MECHANISMS.md) found the suite re-implementing
or ignoring mechanisms Hermes already has. This release adopts
them, in impact order:

- **Every profile gets a SOUL.md.** Hermes loads it from the
  profile's own home into every session — it is the identity slot,
  and the suite never wrote one, so role behavior depended on the
  model happening to consult its skill (field failure: the Router
  asking permission to create a card and apologizing for not
  executing). The Router's SOUL makes dispatch the default action;
  workers get a mandate-bound SOUL. Role skills are additionally
  pinned via the native `skills.auto_load`, so their full text is
  in every session's prompt prefix.
- **Memory seeds.** Each profile's built-in memory
  (memories/MEMORY.md) is seeded once with starting role facts and
  then belongs to the agent — never overwritten, protected on
  uninstall like .env and sessions.
- **Chat entry is verified, not assumed** (closes ASSUMPTIONS
  #10): the new `entry:` config declares a platform for the
  Router; doctor checks it actually reaches the router profile —
  via a gateway.profile_routes entry or a dedicated app in the
  router profile's own .env — and prints the exact fix otherwise.
- **The reminder tick stops duplicating Hermes' notifier.** It
  now announces completions only for cards with NO kanban
  subscription — the CLI-dispatched cards Hermes deliberately
  leaves silent. Subscribed cards are pushed by Hermes itself;
  the journal still records everything.
- **Router skill** uses the board's own structure: parent/child
  card links, attachments, completion contracts / goal mode.

## 0.8.1 — 2026-11-01

- **Profile config.yaml is co-owned now.** Hermes' own setup
  flows (e.g. wiring a messaging platform to a profile) write
  top-level sections into a profile's config.yaml; the installer's
  per-file convergence used to overwrite the file with the render,
  which would silently unwire such a platform on the next
  reconcile. Convergence now merges: rendered keys win, sections
  the suite owns are never resurrected from disk, and foreign
  sections (platforms:, gateway:, …) are preserved verbatim.
  Pinned by a test that adds a platforms.feishu section and
  reconciles twice (preserved, and the second run is a no-op).

## 0.8.0 — 2026-11-01

- **One worker by default.** The general/research/deep trio was a
  template default, not an architecture (the three worker
  templates were byte-identical; the roles differed only in config
  values) — yet every default install paid for three profiles in
  rendering, key sync and failure surface. The shipped template
  now defines ONE worker (general); research and deep ship as
  commented presets, enabled by uncommenting. Existing configs
  that list three workers render exactly as before.
- All workers render from a single shared template
  (profiles/worker/); a per-name template can still override, and
  arbitrary worker names now work — previously a worker whose
  name had no template directory failed the render.
- The Router skill routes by the roles the config actually
  defines instead of assuming the trio exists.

## 0.7.3 — 2026-11-01

- **Out-of-box audit.** The operator's standard: a fresh machine
  must reach the working state with no nursing. Closed in this
  pass: doctor (and the installer's postflight, which reuses it)
  counted a key as present when its NAME existed — an empty `KEY=`
  line read as "in place", the same false green as the field
  failure. Presence now means a non-empty value in the global
  .env, a profile .env, or the process environment. A day-one
  end-to-end test (fresh home, default profile with a model, key
  only in the global .env) pins the contract: one run, inherited,
  keys synced, no key next-steps, no hard errors.
- README quickstart now includes the gateway restart it
  previously glossed over.

## 0.7.2 — 2026-11-01

- **Missing-key output diagnoses instead of asserting.** "Put the
  key in .env" is a false instruction when the operator already
  did and the line is empty or malformed — and the summary still
  cheerfully said "give the Router a task". Now the installer
  states exactly what it found for that variable (no such line /
  line present but value empty / a similar name exists / no '='),
  and the finish line is replaced with the correct sequence while
  any key is missing. .env parsing additionally normalizes BOM,
  zero-width characters and full-width '＝' (an IME slip that
  previously read as "missing").

## 0.7.1 — 2026-11-01

- **The missing-key path no longer asks for a re-run** (field
  report: the installer still printed "re-run the installer" after
  the root fix). Three holes closed: (1) the next-step text now
  says the .env line is the ONLY step — propagation is automatic;
  (2) auto-reconcile now triggers on keys that were never synced
  (absent at install time, added later), via a comparative check
  over each role's resolved key variable, not only on recorded
  baselines; (3) .env parsing accepts `export ` prefixes and
  quoted values, which previously read as "missing".

## 0.7.0 — 2026-11-01

- **The suite owns no providers or models at all.** Following the
  operator's doctrine to its conclusion: superagent.yaml is now
  selections only. A role's `provider`/`model` names resolve
  against the default Hermes profile's own config — its `model:`
  block, `providers:` mapping and `custom_providers:` list — and a
  selected named endpoint is rendered into the profile the way
  Hermes' own profile seeding does it (model block pointing at
  `custom:<name>`, entry copied verbatim alongside). Selecting
  something Hermes does not have fails the install with the menu
  of what exists. New providers are added in Hermes (Settings ->
  Providers / hermes setup) and become selectable immediately.
- **`hermes superagent providers`** lists what can be selected.
- Verbatim model blocks are now rendered whole (previously three
  fields were picked out and the rest silently dropped), and the
  default block's referenced named entry travels with inherited
  roles too.
- Doctor derives key variables from each role's resolved
  selection; the template ships without a `providers:` section.
  Pre-0.7 suite-owned `providers:` keep working unchanged (legacy).

## 0.6.2 — 2026-11-01

- **Keys have a single source of truth: ~/.hermes/.env.** The
  fill-gaps-only key sync protected a hypothetical per-profile key
  and broke the real workflow — rotate the key in the global file
  and the profiles kept sending the old one (operator's verdict:
  point fixes, no global thinking). The installer now CONVERGES
  each profile's suite-managed key variables onto the global value,
  and the auto-reconcile from 0.6.1 also triggers on key drift, so
  a rotation propagates by itself (next command, or within one
  reminder tick) with no upgrade run and no hand-editing of
  profile files. state.json records value hashes (never values)
  so drift is detectable without reading secrets.
- **Doctor checks key convergence**, not just presence: a profile
  copy that differs from the global .env is now an error finding
  (presence-only was the false green that masked this class).

## 0.6.1 — 2026-11-01

- **Config edits apply themselves.** Requiring `upgrade` after
  editing superagent.yaml was a ritual, not a mechanism (operator's
  verdict). The suite now reconciles on its own: any
  `hermes superagent` command, and the reminder tick within one
  cycle, re-renders the profiles when the config is newer than the
  install state. A failed apply is reported once per config
  version, never spammed.
- **`hermes superagent set-model <profile> <model>`**: one command
  edits superagent.yaml (as a comment-preserving text edit) and
  applies it. `inherit` clears the override.

# Changelog

## 0.6.0 — 2026-11-01

- **Zero-config inheritance (the operator's design call).** The
  suite no longer asks anyone to re-declare a provider they already
  have. Any role left without a model inherits the default Hermes
  profile's `model:` block verbatim at install time — provider
  string included, so provider types beyond the suite's own
  abstraction work too. Consequences:
  - a first install on a machine whose default profile already
    talks to a model completes in ONE run (previously: generate
    template, stop, fill it in, run again);
  - superagent.yaml is now an override file: fill in only what a
    role should do differently from the default;
  - **the installer syncs API keys itself**: each profile's `.env`
    is filled (gaps only — an existing per-profile value is that
    profile's own and is never overwritten) from `~/.hermes/.env`.
    The manual copy-the-key-into-every-profile script is retired;
    the operator's only key job is keeping `~/.hermes/.env` right.
  Validation relaxes accordingly (model-less roles warn as
  "will inherit", the verbatim provider is accepted).

## 0.5.7 — 2026-11-01

- **Profiles are living directories; the installer no longer
  replaces them wholesale.** The convergence bug behind a day of
  confusing failures: every reinstall whose render differed deleted
  each profile directory and re-created it from the render —
  including the profile's `.env` (the API key), sessions, and logs.
  The profile then failed every model request (`request_failed`)
  while doctor kept reporting the key "in place", because it also
  counted the global `.env`. Fixes: profiles converge per-file
  (only rendered files are managed), state records only managed
  files (skills included), snapshots/rollback/uninstall touch only
  managed files and explicitly protect `.env`, `sessions/`, `logs/`,
  and `memory/` even in legacy states. Regression-tested by
  planting a `.env` and a session file across a config-change
  reinstall and an uninstall.
- After upgrading, restore any already-lost profile `.env` once
  (copy the key line from `~/.hermes/.env`); the installer will
  never delete it again.

## 0.5.6 — 2026-11-01

- **Doctor no longer judges the machine's DNS.** The fake-IP check
  probed a third-party hostname's resolution and reported on the
  machine's proxy setup as if it were suite health — that is one
  operator's environment, not a general criterion (called out in
  the field). Replaced with a config-consistency check: doctor
  verifies `security.allow_private_urls` only when the config
  itself declares it — declared on means every profile must have
  it rendered, declared off means none may, undeclared means no
  opinion. The live DNS probe is gone.

## 0.5.5 — 2026-11-01

- **The installer no longer needs PyYAML at all.** 0.5.4's
  interpreter probe was defeated from inside the Hermes process:
  there, `python3` resolves to Hermes' own bundled python (its
  tools directory leads the PATH), so every probe candidate lacked
  PyYAML and the upgrade still died at the install step. Removed
  the dependency instead of probing harder: install.py,
  validate_config.py, and render_profiles.py all fall back to the
  bundled miniyaml parser (now also covering PyYAML's indentless
  sequence style, caught by a blocked-yaml end-to-end install
  test). Side effect: previously installed upgrade commands start
  working again, because the installer they invoke no longer dies.

## 0.5.4 — 2026-11-01

- **Root cause of the multi-day "config not loaded" saga, fixed.**
  Hermes' bundled CLI python ships no PyYAML; every `import yaml`
  in the plugin silently failed, so the suite config, the profile
  configs, and the default config all read as empty — doctor
  reported a perfectly valid config as missing while several other
  checks vacuously passed on empty data. Fixes:
  - the plugin bundles `miniyaml`, a subset parser covering the
    suite's config grammar, and `_yaml_load` falls back to it when
    PyYAML is not importable (equivalence-tested against PyYAML on
    the shipped template and a filled config);
  - `hermes superagent upgrade` now probes for a PyYAML-capable
    interpreter before running the installer, instead of blindly
    using the plugin's own interpreter (which is how the 0.5.3
    upgrade pulled successfully, then died at the install step).

## 0.5.3 — 2026-11-01

- **All script and plugin output is English now.** The installer,
  uninstaller, doctor findings, journal digest, reminder lines, and
  CLI messages previously printed Chinese prose (an operator-local
  choice from the first field sessions); every user-facing string
  has been translated, including the installer's postflight
  classifier keys. Test fixtures still use Chinese task titles where
  they stand for user content — that is data, not output.

## 0.5.2 — 2026-11-01

- **Bootstrap install; nothing lives outside Hermes' directory.**
  Operator's standing preference: no program checkouts scattered in
  the home directory. New `bootstrap.sh` (one curl line in the
  README) clones the suite into its managed source home
  `~/.hermes/superagent/src` — alongside the plugin, profiles,
  config, and history, which already lived under `~/.hermes/` — and
  runs the installer from there. A stuck managed clone re-clones
  itself (it holds no user data). The checkout-based flow remains,
  documented as the development path.

## 0.5.1 — 2026-11-01

- **`hermes superagent upgrade`.** Field lesson, same morning: the
  upgrade runbook depended on the operator remembering where the
  source checkout lives — on the operator's machine it did not exist
  at the assumed path, so several "installs" silently never ran
  while diagnostics chased the old plugin. An installed suite now
  upgrades itself: state.json records `source_repo` + `repo_url` at
  install time; the upgrade command pulls the recorded checkout —
  or, if it is gone, maintains its own clone at
  `~/.hermes/superagent/src` — and runs that installer against the
  home. The operator's filing system is no longer part of the
  upgrade path.

## 0.5.0 — 2026-11-01

The install/update system, rebuilt instead of patched (operator's
call after a morning of upgrade friction: a `git pull` blocked by
the user's own config, three places a config could live, a bash
installer that had accreted a step per incident).

- **One command, declarative.** `scripts/install.py` replaces the
  bash installer (`install.sh` is now a shim). Fresh install,
  upgrade, and repair are the same idempotent convergence: desired
  state is computed, only differences are applied, and a second run
  reports "no changes". `--force` and the collision dance are gone.
- **Config has exactly one home.** The repo ships templates only.
  First run writes the guided config template to
  `~/.hermes/superagent/superagent.yaml` and stops (exit 3); fill it
  in, run the same command again. `pick_config.py` and the staging
  rules are deleted — there is nothing left to pick between.
- **Version is single-sourced** in `VERSION`; `scripts/release.sh`
  syncs the recorded copies and runs the tests; the installer stamps
  the version into the installed plugin.
- **State contract + rollback.** Installs record `state.json`
  (paths + content hashes). The previous generation is snapshotted
  to `superagent/prev/` before any change — code artifacts only,
  never the user's config or journal — and
  `./install.sh --rollback` restores it. Legacy `manifest.json`
  installs migrate automatically; a manifest is still written for
  older tooling.
- **Verification is part of install.** The run ends by executing the
  doctor checks in-process; hard errors fail the install instead of
  printing "Done", and operator-side items (the key line, plugin
  enablement settling) are reported as next steps, not failures.
- **Uninstall is state-driven too** (`scripts/uninstall.py`), and
  keeps the operator's config and history by default — `--purge`
  removes them.

117 tests passing, including the full installer cycle: two-phase
first run, seeding, idempotent re-run, config-change re-render,
legacy migration, rollback, and uninstall keeping user data.

## 0.4.1 — 2026-11-01

- **The `git pull` config conflict is structurally dead.** Field
  report: the operator's filled config lived in the tracked
  `config/superagent.yaml`, so every upgrade pull aborted with
  "local changes would be overwritten". Two changes close the class:
  (1) first-install staging moves to `config/superagent.local.yaml`
  (already gitignored via `*.local.yaml`); SETUP.md and the README
  manual path now write there and pass it via `--config`.
  (2) `pick_config` now treats the installed copy as the source of
  truth unconditionally: once `~/.hermes/superagent/superagent.yaml`
  holds real values it wins over any repo-side candidate, so the
  repo tree never again holds values worth fighting over.

## 0.4.0 — 2026-11-01

Proactive reminders for unclosed work — the mechanism that separates
an assistant from a tool you have to poll. Design (operator-approved):
four layers — a durable ledger, event + schedule triggers, a
judgement pass before anything is said, and anti-nagging discipline.

- **Reminder ledger** (`plugin/superagent/reminders.py`): situations
  that need the person — a card **blocked**, **stalled**, or **done
  but unreviewed** — are fingerprinted by task + state + the epoch
  the state began. Each is announced once, then re-announced only
  after a backoff that doubles each time (1h → 2h → 4h …, capped at
  24h). A state change re-arms; closing a task prunes its row.
  Inspect it any time with `hermes superagent reminders`.
- **Timed driver**: the installer drops a no-agent cron script
  (`~/.hermes/scripts/superagent-reminder-tick.py`) and registers a
  Hermes cron job for it (every 10 minutes). In no-agent mode the
  script's stdout is the delivery — Hermes' cron router sends it to
  the chosen platform; a tick with nothing due prints nothing and
  stays silent. Urgent items (blocked/stalled) get a line each;
  finished-unreviewed work folds into one gentle summary line. Set
  the delivery target once: `hermes cron edit <id> --deliver feishu`.
  If registration fails on a given Hermes version, the installer
  prints the exact command instead of failing.
- **Judgement stays with the Router**: the tick applies the
  deterministic discipline (freshness, dedupe, backoff); the Router
  skill's reminder protocol covers the conversational side —
  re-check before repeating, never re-announce what was already
  acknowledged, one message per situation, calmer tone for older
  waits.
- Watchdog runs now also pass through the reminder ledger (due items
  are recorded and stored in the outbox, store-first as always).

113 tests passing. Sandbox-verified end to end: tick 1 announces a
blocked card and folds a finished one into the summary line, tick 2
is silent (backoff), a fresh block episode re-arms and announces
again, and uninstall leaves nothing behind.

## 0.3.1 — 2026-11-01

- **Plugin-not-loaded: root cause found and fixed.** Reading Hermes'
  plugin gate in source (`hermes_cli/plugins_discovery.gate_manifest`)
  settled it: user plugins are opt-in — the loader silently skips
  (DEBUG log only) any plugin whose key is not in `plugins.enabled`,
  and a fresh install's migration grandfathers only plugins present
  at migration time. Ours was installed afterwards, so it never
  loaded and `hermes superagent …` did not exist. The installer now
  runs `hermes plugins enable superagent`; `doctor` checks the
  enablement state (missing list / not listed / disabled-wins) with
  the fix attached. ASSUMPTIONS item 3 records the mechanism.
- **`hermes superagent recall <关键词>`** — search the journal by
  keyword and get matching past outcomes in prose. Global memory is
  only useful if it can be *recalled*, not just written.
- **Doctor: install-drift checks.** Warns when the suite config was
  edited after the last install (rendered profiles are stale) and
  when the plugin version and the install manifest disagree (a
  half-finished upgrade).

101 tests passing; sandbox-verified: install issues the enable call,
doctor flags a missing enablement with its fix and clears it once
enabled, recall hits and misses behave.

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
