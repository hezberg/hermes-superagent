# Hermes Native Mechanisms — Source Survey for hermes-superagent

Survey of NousResearch/hermes-agent (local clone, main branch as of 2026-11-01),
conducted to find where the superagent suite should stop building parallel
mechanisms and configure/use Hermes-native ones instead. Every claim is backed
by a repo-relative path; anything not found in source is marked UNVERIFIED or
NOT FOUND. Verdicts are relative to the suite's current implementation
(installer-rendered profiles, plugin with Gate/journal/outbox/reminders,
Router/Worker skills planted per profile, no-agent cron tick).

---

## Q1. Profile anatomy

**Mechanism.** A profile home IS a `HERMES_HOME` (`~/.hermes/` for default,
`~/.hermes/profiles/<name>/` for named profiles); all lookups resolve via
`get_hermes_home()`. Seeded dirs (`hermes_cli/profiles.py:40`):
`_PROFILE_DIRS = ["memories", "sessions", "skills", "skins", "logs", "plans",
"workspace", "cron", "home"]`. A profile home can also hold `config.yaml`,
`SOUL.md`, `.env`, `auth.json`, `profile.yaml`, `state.db`, `system_prompt.md`,
`plugins/`, `mcp.json`, `knowledge/`, `preferences/`, `scripts/`.

**What `hermes profile create` seeds** (`hermes_cli/profile_cmd.py` →
`hermes_cli/profiles.py:create_profile()` →
`hermes_cli/profiles_initialization.py:finish_profile_layout()`):

- the `_PROFILE_DIRS` tree (empty);
- **model block only**, copied (not linked) from the active profile —
  `_seed_model_config()`: *"Copy (not link) the active profile's model block
  into a fresh profile so it is usable; profiles stay independent islands
  afterwards."* (This validates the suite's render-time inheritance design.)
- an empty `.env` (0600) with a placeholder header;
- a default `SOUL.md` (`hermes_cli/default_soul.py:DEFAULT_SOUL_MD`);
- bundled skills copied in via `tools/skills_sync.sync_skills()` (or, with
  `--no-skills`, only the essential `hermes-agent` skill).
  NOT seeded: `MEMORY.md`/`USER.md`, plugins, the rest of `config.yaml`.

**Auto-loaded into every session** (vs on-demand):

| Item | Auto-loaded? | Evidence |
|---|---|---|
| `<profile>/SOUL.md` | **Always** — identity slot #1 of the stable prompt tier | `agent/system_prompt.py:_identity_parts()` → `agent/prompt_builder.py:load_soul_md()` reads `(home_override or get_hermes_home())/"SOUL.md"`, scoped to the agent's OWN home |
| `<profile>/memories/MEMORY.md`, `USER.md` | **Always**, as a frozen snapshot at session start (if `memory.memory_enabled` / `memory.user_profile_enabled`) | `tools/memory_tool.py` header; `tools/memory_tool_store.py:format_for_system_prompt()` |
| Skills index (name+description) | Always | `agent/prompt_builder.py:build_skills_system_prompt()` |
| Skills in `skills.auto_load` | **Full body always** | see Q3 |
| Project context files (`.hermes.md`/`AGENTS.md`/…) | Always, but discovered from **cwd/git tree, NOT the profile home**; only one type wins | `agent/prompt_builder.py:build_context_files_prompt()` |
| `sessions/`, `state.db`, `cron/`, full skill bodies | On-demand / runtime only | — |

Behavior-shaping `config.yaml` keys: `agent.system_prompt` (user overlay,
injected ephemerally at API-call time; `hermes_cli/personality.py`), named
`personalities` selected via `display.personality`, `agent.coding_instructions`,
`agent.environment_hint`, `context_file_max_chars` (caps SOUL.md etc.).
`custom_instructions` as a config key: NOT FOUND.

**Verdict: suite should adopt** — the suite renders profiles but does not seed
per-role `SOUL.md`; role behavior currently rides on skills being picked up
from the index (see field failure in Q8). Hermes gives every profile a
guaranteed always-in-context identity file; the Router's default behavior
belongs there.

## Q2. Memory system & providers

**Built-in memory.** Per profile, no exceptions:
`tools/memory_tool.py:get_memory_dir()` returns `get_hermes_home()/"memories"`,
so each profile has its own `MEMORY.md` / `USER.md`. Defaults
(`hermes_cli/config_defaults.py`): `memory.memory_char_limit: 2200`,
`memory.user_char_limit: 1375`, `memory.memory_enabled: True`,
`memory.user_profile_enabled: True`, `memory.write_approval: False`,
`memory.nudge_interval: 10`, `memory.provider: ""`. Entries are `§`-delimited;
the `memory` tool supports add/patch/remove plus atomic batches
(`tools/memory_tool_store.py`). Injection is a **frozen snapshot at session
start** — mid-session writes hit disk (under a file lock) but never change the
running prompt, only the next session / post-compression rebuild.

**Providers.** One external provider at a time via `memory.provider`
(`agent/memory_provider.py:MemoryProvider`; lifecycle
initialize → system_prompt_block/prefetch/sync_turn per turn → shutdown, with
`on_session_end/on_pre_compress/on_memory_write/on_delegation` hooks). Provider
runs **alongside** built-in memory, not instead of it. In-tree code ships only
`plugins/memory/byterover/` and `plugins/memory/retaindb/`; Honcho, Mem0,
Supermemory, Hindsight, OpenViking, Holographic etc. are catalog-installed
plugins living in `$HERMES_HOME/plugins/` with per-profile config files
(`$HERMES_HOME/<provider>.json` or `<provider>/`).

**Can two profiles share one backend?** Core enforces per-profile binding
("One instance, one profile", `agent/memory_manager.py`,
`agent/memory_caller_scope.py`), and local/provider state is derived from the
profile's own home — but the *underlying store* sharing depends on the
provider's partition key:

- **Honcho — shared by design**: one global **user peer** across profiles +
  one AI peer per profile (`hermes.<profile>` host key), all in one workspace.
  Docs: *"the user peer is global across profiles"*; *"All Hermes profiles
  under one workspace see the same user identity."* (`website/docs/user-guide/features/memory-providers.md`, `hermes_cli/profiles_honcho.py`)
- **RetainDB**: project auto-derived as `hermes-<profile>`; deliberately
  setting the same `RETAINDB_PROJECT` in two profiles shares the partition.
- **Mem0**: defaults `user_id: hermes-user`, `agent_id: hermes` (not
  profile-derived) — same key + defaults = shared/colliding unless changed.
- **Supermemory**: `container_tag` defaults to `hermes` (shared); supports
  `hermes-{identity}` templating for per-profile isolation, plus opt-in
  shared custom containers.

**Native global/shared memory scope for built-in memory: NOT FOUND.** Sharing
exists only as a provider-level, deliberate configuration.

**Verdict: partially adopt** — per-profile built-in memory already aligns with
the suite's profile model (role learnings should live in each role profile's
own `memories/`). The suite's journal is a task ledger, not a memory store, so
it does not duplicate built-in memory; but for a *cross-profile user model*
(the thing no suite file currently provides natively), Honcho is the
off-the-shelf answer and should be offered as an optional installer choice,
not reimplemented.

## Q3. Skills: always-on

**Mechanism — yes, natively: `skills.auto_load`.**
`hermes_cli/config_defaults.py:1447`:

> "Skill names pinned as fully loaded in every new session (CLI, TUI,
> gateway, cron, API)."

`agent/skill_commands.py:resolve_auto_load_skills()` /
`build_auto_load_prompt()` render each listed skill's full body into the
stable prompt prefix, framed as *"The "{name}" skill is auto-loaded via
config (skills.auto_load). Treat its instructions as active guidance for
the duration of this session…"*. Suppressed by `--ignore-rules` /
`HERMES_IGNORE_RULES`; also available per-session via CLI `-s/--skills`.
Normal skills are otherwise index-only (name + description in the prompt;
body on demand via `skill_view`). Per-profile skills live in
`<HERMES_HOME>/skills`; search precedence: project > local profile >
`skills.create_dir` > `skills.external_dirs` (`agent/skill_utils.py`).
`skills.disabled` / `skills.platform_disabled.<platform>` exist as deny lists.

**Verdict: suite should adopt** — set `skills.auto_load` in each rendered
profile's `config.yaml` (Router skill on sa-router, Worker skill on workers)
instead of depending on the model noticing the skill in the index. This is a
one-line-per-profile render change with a native guarantee behind it.

## Q4. Kanban

**Implementation.** `hermes_cli/kanban_db.py` (+ `kanban_db_boards.py`,
`kanban_db_dispatch.py`, `kanban_db_graph.py`, `kanban_db_notify.py`,
`kanban_db_workspace.py`), tools in `tools/kanban_tools.py`. The board is
**shared across profiles by design** — DB at the shared Hermes root
(`<root>/kanban.db`; extra boards under `<root>/kanban/boards/<slug>/`),
explicitly NOT resolved through the active profile's home. Board selection:
`board=` arg > `HERMES_KANBAN_BOARD` > `HERMES_KANBAN_DB` > current-board
file > `default`. There is no `kanban.board` YAML key.

**Native surface the suite can use** (all in the `tasks` schema / tools):
attachments (`task_attachments`, `kanban_attach`/`kanban_attach_url`, 25 MB
cap), comments (`task_comments`, `kanban_comment`), subscriptions
(`kanban_notify_subs`, see Q11), **links/dependencies** (`task_links`;
children stay in `todo` until all parents are `done`, then auto-promote to
`ready`; cycles rejected), priority (dispatcher tiebreaker), workspace kinds
(`scratch`/`dir`/`worktree` + `branch_name`, `project_id`), per-card
`model_override`/`provider_override`/`reasoning_effort`, `goal_mode`,
`max_retries`, `completion_contract`, `idempotency_key`,
`block_kind ∈ {dependency, needs_input, capability, transient}`.
Workflow: `triage, todo, scheduled, ready, running, blocked, review, done`
(+ `archived`). @mentions: NOT FOUND. Labels/tags: NOT FOUND (closest:
`tenant`, `project_id`).

**Wake/dispatch.** Gateway-embedded dispatcher by default
(`gateway/kanban_watchers.py`, `gateway/kanban_watchers_dispatcher.py`;
config `kanban.dispatch_in_gateway: True`,
`kanban.dispatch_interval_seconds: 60`; standalone `hermes kanban daemon`
also exists). A tick reclaims stale work, promotes ready children, claims a
card (CAS + `task_runs` row) and spawns one worker per run
(`hermes_cli/kanban_db_dispatch.py:_default_spawn`) with env
`HERMES_KANBAN_TASK`, `HERMES_KANBAN_DB/BOARD/RUN_ID/CLAIM_LOCK/WORKSPACE`,
`HERMES_PROFILE=<assignee>`, `HERMES_HOME=<profile home>`; execution is
submitted to the assignee profile's owner gateway
(`hermes_cli/kanban_worker_client.py`, `gateway/session_kanban.py`).
Heartbeats: explicit `kanban_heartbeat` tool plus automatic activity
mirroring (`tools/kanban_tools.py:_touch_activity`); claim TTL 15 min,
heartbeat staleness backstop 1 h (see Q13).

**Verdict: suite should adopt more** — it already builds on kanban as the
coordination primitive (aligned), but underuses: attachments (vs the suite's
outbox/file passing), parent/child links for decomposed work,
`completion_contract`, and notify subscriptions (Q11). @mentions and labels
do not exist natively — anything built on them would be suite-side.

## Q5. Gateway routing to a non-default profile

**Mechanism — fully native, on by default.** `gateway.multiplex_profiles`
(default `true`; env `GATEWAY_MULTIPLEX_PROFILES`;
`gateway/config.py`, `hermes_cli/gateway_multiplex_mode.py`,
`website/docs/user-guide/multi-profile-gateways.md`): one gateway process
(the default profile's) serves every profile — *"the default profile plus
every served named profile get their own adapters, secrets, sessions, and
cron ticks"*. Served set: `hermes_cli/profiles.py:profiles_to_serve()`,
re-scanned live.

Two binding styles:

1. **Per-profile bot**: each profile home has its own `config.yaml`/`.env`
   platform credentials (Feishu: `FEISHU_APP_ID`, `FEISHU_APP_SECRET`,
   `FEISHU_HOME_CHANNEL`, … in the profile's own `.env`); the multiplexer
   brings up that profile's platforms under its own credentials.
2. **Shared bot + routing rules**: `gateway.profile_routes`
   (`gateway/profile_routing.py`) — conjunctive matching on
   `platform, chat_id, thread_id, user_id, guild_id` (+ `bot_profile`),
   highest specificity wins, *"Routing works on every platform adapter"*,
   so `platform: feishu` qualifies. Routes require multiplexing on; a route
   to an unserved profile fails closed.

A separate gateway process per profile is now the exception
(`gateway.standalone: true` in a named profile). `HERMES_PROFILE` is NOT
the routing key (selection is `-p/--profile` → `HERMES_HOME`).

**Verdict: suite should adopt** — this closes the suite's long-open
ASSUMPTIONS #10. Binding Feishu to `sa-router` is configuration
(`gateway.profile_routes` on the default profile, or a Feishu app in the
router profile's own `.env`), not missing Hermes functionality. The
installer should write/verify it and doctor should check it.

## Q6. Cron

**Mechanism.** Jobs are **per-profile by design**: stored at
`<HERMES_HOME>/cron/jobs.json` — *"a job authored in profile `coder` lives
in `~/.hermes/profiles/coder/cron/jobs.json` and executes with `coder`'s
`.env`, `config.yaml`, and skills"* (`cron/jobs.py`). The gateway ticks
every 60 s, and under multiplexing ticks **each served profile's own
store**. Job fields include `prompt, script, no_agent, deliver,
failure_deliver, origin{platform,chat_id,thread_id}, schedule, repeat,
attach_to_session`, etc. (`cron/jobs.py:create_job`,
`cron/job_definition.py`).

**no-agent mode** (`cron/scheduler.py:_run_no_agent_job`): the script IS
the job — stdout is delivered verbatim, empty stdout (or `wakeAgent=false`)
is silent success, non-zero exit → error alert. `deliver` targets
(`cron/scheduler_delivery.py`): `local` (file only), `origin` (creation
chat, home-channel fallback), `all` (every platform with a home channel),
bare platform name (→ its home channel), `platform:chat_id[:thread_id]`,
`bot-chat[:<profile>]` (inject as a real inbound turn), `webhook`.
There is **no separate reminder subsystem** — cron one-shots ARE Hermes'
reminder mechanism (`cron/blueprint_catalog.py` even ships a
"custom-reminder" blueprint that compiles to an ordinary job).

**Verdict: suite already aligns** — the suite's no-agent tick + `--deliver`
usage is the native pattern. Two refinements available natively: use
`failure_deliver` for tick failures, and note the tick lives in whichever
profile's store it was created in (per-profile scoping cuts both ways).

## Q7. Delegation (native subagents)

**Mechanism.** `delegate_task` (`tools/delegate_tool.py` + dispatch/child-run
modules, `tools/async_delegation.py`): spawns ephemeral child agents,
default **synchronous** (results return in the tool result); `background=True`
(or `delegation.gateway_mode: background`) returns a handle and results
*"re-enter the conversation as their own new message when that unit
finishes"*. Config (`delegation.*`): `max_spawn_depth` default 1 (children
cannot recurse unless `role="orchestrator"` + `orchestrator_enabled`),
`max_concurrent_children` default 10, `max_iterations` 250, per-child
model/provider overrides, `subagent_auto_approve` default false. An advanced
backend can route children by profile (`delegation.backend: profile_routes`
— a listed profile's subagents use *its* credentials, pool, SOUL.md and
terminal policy).

**vs kanban** (docs, `website/docs/user-guide/features/kanban.md`):
delegation children are in-process, parent-scoped, and die with the
turn/gateway — *"If the gateway goes down mid-child, the child is retired,
never resumed. Work that must outlive the gateway, or needs its own
reviewer, still belongs in child cards."* Kanban tools are actively
stripped from delegation children (`tools/kanban_tools.py`).

**Verdict: suite already aligns** — kanban is the right primitive for the
suite's durable, cross-profile, reviewable work. Native delegation is the
better tool only for quick in-turn fan-out inside one profile (e.g. a
worker parallelizing research subtasks); the Worker skill may mention it,
but it cannot replace cards.

## Q8. Hooks/plugins for context injection — and why static behavior doesn't need them

**Plugin surface.** Hook registry `hermes_cli/plugins.py:VALID_HOOKS`
(dispatch `hermes_cli/plugins_dispatch.py:invoke_hook`) includes
`pre_llm_call`, `post_llm_call`, `pre_tool_call` (the only fail-closed
veto hook), `transform_llm_output`, `pre_gateway_dispatch`,
`on_session_start/end`, `subagent_start/stop`, and kanban lifecycle hooks
(`kanban_task_claimed/completed/blocked`, `on_kanban_worker_spawned/exited`,
`on_kanban_dispatch_tick`, …). Power per hook:

- `pre_llm_call` may return `{"context": "…"}` — appended to the current
  turn's **user message**, explicitly *not* the cached system prompt
  (`website/docs/developer-guide/prompt-assembly.md`), or
  `{"action": "block"}` to end the turn.
- Plugins can also `register_system_prompt_section` (position `after_memory`
  only, ≤4000 chars/section, ≤32 sections), `register_tool/skill/command`.
- Plugin enablement is per-profile: user plugins live in
  `<HERMES_HOME>/plugins/`; `plugins.enabled` is an opt-in allow-list and
  `plugins.disabled` wins over it (`hermes_cli/plugins_discovery.py`).
- Gateway shell hooks (`~/.hermes/hooks/<name>/HOOK.yaml` + `handler.py`)
  observe gateway/session/agent events but cannot inject prompt content
  and never block the pipeline. `gateway/builtin_hooks/` ships nothing.

**The native static alternative.** For static role behavior, Hermes already
guarantees two always-in-context, per-profile channels that need no plugin
at all: `SOUL.md` (identity slot #1, Q1) and `skills.auto_load` (Q3), plus
the ephemeral `agent.system_prompt` overlay. The field failure that
motivated this survey — sa-router replying like a generic assistant and
offering to "create a task to organize the analysis" instead of working in
role — is exactly what these channels exist to prevent; a plugin hook
injecting the same text per-turn would be strictly worse (user-message
position, no prefix-cache stability, plugin must be enabled per profile).

**Verdict: suite should adopt SOUL.md + auto_load for role behavior;
hooks remain the right tool only for enforcement** (e.g. a future Gate
hardening via `pre_tool_call`/`pre_gateway_dispatch`, and
`kanban_task_completed` as a notification trigger — see Q11).

## Q9. Notifications — what reaches the human natively

Native proactive paths (evidence in Q5/Q6/Q11):

1. **Kanban notifier**: gateway polls `kanban_notify_subs` every 5 s and
   delivers terminal events (`completed, blocked, gave_up, crashed,
   timed_out, review_requested, …`) as chat messages, optionally waking
   the origin agent (`gateway/kanban_watchers.py`,
   `gateway/kanban_watchers_notifier.py`).
2. **Cron delivery**: agent and no-agent jobs deliver to
   origin/home-channel/arbitrary targets (Q6).
3. **Gateway home-channel notices**: startup/restart and housekeeping
   broadcasts to `platforms.<p>.home_channel` (`gateway/run_notifications.py`)
   — gateway's own events only, not a general bus.
4. **Background completions**: async delegation / background processes
   re-enter through the owning profile's adapter, including routed
   profiles via the shared bot.

The suite's journal (append-only terminal-state ledger under
`~/.hermes/superagent/`) does not duplicate any of these: nothing native
keeps a cross-board, queryable completion history. The suite's reminder
ledger overlaps only with (1) — and only for cards that have subscribers
(see Q11/Q13 for the gap).

**Verdict: partially adopt** — keep the journal (no native equivalent);
shrink the reminder layer to the gap native notification doesn't cover.

## Q10. Profile inheritance — what profiles do NOT inherit

**Profiles are islands.** Beyond the creation-time copies in Q1, there is
**no runtime inheritance** from the default profile:

- **`.env`: no root fallback.** `hermes_cli/profiles.py:backfill_profile_envs`:
  *"It never copies the default's `.env`: secrets are profile-scoped."*
  `hermes_cli/env_loader.py:load_hermes_dotenv()` loads the active home's
  `.env` only; under multiplexing, `agent/secret_scope.py` builds a
  per-profile secret scope and unscoped lookups *raise* rather than fall
  back. The only cross-profile env layer is the administrator **managed
  `.env`** (policy layer, applied last with override).
- **`state.db` is per profile** (`hermes_state.py`: `get_hermes_home()/"state.db"`).
  Only gateway process state (`gateway_state.json`, `profile_routes`,
  the HTTP listener) is shared, in the default home.
- **Skills** are copied into each profile at create/update, not read live
  from the default profile. Sharing by reference is opt-in per profile via
  `skills.external_dirs`.
- **MCP servers** are defined per profile (`mcp_servers` in that profile's
  `config.yaml`, secrets resolved under the owner profile's scope) — with a
  documented process-global discovery limitation (`#67605`).
- Cron, plugins, hooks, memory, SOUL, sessions: all per-profile (Q1/Q2/Q6/Q8).
- No `inherit`/`fallback_config` key for whole profiles: NOT FOUND.

**Verdict: suite already aligns** — the suite's design (render-time copy of
the default profile's model/providers; installer-side key convergence into
each profile `.env`) mirrors Hermes' own seed-and-isolate semantics, and
the key-convergence machinery is *necessary*, not redundant: Hermes will
never fall back to the root `.env` for a profile session. One optional
simplification: role skills could be shared via `skills.external_dirs`
instead of copied per profile, at the cost of per-profile independence.

## Q11. Task-completion notification to the HUMAN (the field failure)

**Native paths, precisely:**

- **Auto-subscribe on create** (`tools/kanban_tools.py:_maybe_auto_subscribe`,
  gate `kanban.auto_subscribe_on_create: True`): when a card is created from
  a **gateway messaging session**, a `kanban_notify_subs` row is written
  with `delivery_mode="notify+wake"`; from a **TUI/desktop session**, a
  `platform="tui"` sub is written (delivered by the TUI poller *while that
  session is live*); `api_server` sessions get wake-self-post subs.
  Children inherit their parents' subs.
- **Delivery engine** (`gateway/kanban_watchers.py:_kanban_notifier_watcher`,
  gate `kanban.notify_in_gateway: True`, 5 s poll): for each terminal event
  it sends a chat message to the subscribed chat (`✅ <task> completed…`,
  artifacts uploaded as native files) and, in `notify+wake` mode, wakes the
  origin agent with a synthetic turn carrying the handoff summary
  (`gateway/wake.py:deliver_wake`). Subs survive `done` (removed on
  `archived`); 12 consecutive send failures drop a sub; stale subs GC after
  `kanban.done_sub_retention_days: 30`.
- **Explicit subscription**: `hermes kanban notify-subscribe` (CLI) and the
  dashboard's home-subscribe (`plugins/kanban/dashboard/plugin_api.py`),
  which subscribes a platform's home channel to a specific card.

**The CLI hole — confirmed in source.** `HERMES_SESSION_ID` is
*deliberately* not a subscription fallback: *"it is set for every CLI/ACP
invocation and would auto-subscribe every CLI run."* Shell
`hermes kanban create` never subscribes at all. So a card created from a
plain `hermes --profile sa-router` CLI chat gets **no subscription, no
message, no wake** — completion exists only in `kanban.db`/`task_events`
until a human polls. There is also **no home-channel fallback**: kanban
never auto-delivers to `platforms.<p>.home_channel` for unsubscribed cards
(NOT FOUND in `config_defaults.py` or the notifier).

**Verdict: partially native — build the gap only.** Gateway/TUI-originated
work is fully covered (configure: create cards from the Feishu/gateway
entry, which Q5 now makes possible, and native notify+wake does the rest).
The CLI-origin gap is real and suite-shaped: either (a) the suite
explicitly subscribes a chosen user chat at card-creation time from the
Router, or (b) the suite's existing cron tick detects terminal events for
unsubscribed cards and delivers them — which is precisely the niche the
suite's outbox/reminder machinery should shrink to.

## Q12. Memory self-organization ("dreaming")

**What runs automatically in core:**

- **Background review fork**: every `memory.nudge_interval` (default 10)
  user turns
  (`agent/turn_context.py:_tick_memory_nudge()`), a post-turn fork asks
  *"should any skill/memory be saved or updated?"* and writes directly to
  the built-in memory + skill stores (`agent/background_review.py`,
  `agent/turn_finalizer.py` — runs after delivery; suppressed for cron
  agents). Unattended patch/remove of memory is gated by
  `memory.write_approval` / the background delete gate.
- **Provider auto-extraction**: with an external provider configured, every
  completed turn is synced (`run_agent.py:_sync_external_memory_for_turn()`
  → `MemoryManager.sync_all()`), session end/rotation flushes extraction
  (`commit_memory_session()` → `on_session_end`), and pre-compaction hooks
  feed insights into the summary (`agent/conversation_compression.py`).
  In-tree example: ByteRover `memory.byterover.auto_extract` (default true).
- **Built-in `MEMORY.md` has NO `on_session_end` extraction** — the hooks
  above are provider-only; built-in memory learns only via the background
  review fork and explicit `memory` tool calls.

**What does NOT exist in core:** no periodic/time-based consolidation, no
"dreaming" pass (`dream*` in agent/tools/gateway/cron: NOT FOUND; core
cron involvement in memory: NOT FOUND — review is turn-count-triggered,
in-process). The only dreaming implementation is a third-party catalog
plugin, `plugin-catalog/hermes-dreaming.yaml` ("Nightly deterministic
memory consolidation"), installed explicitly, which works through
ordinary cron jobs + the regular `memory` tool and writes
`$HERMES_HOME/memories/DREAMS.md`. `agent/curator.py` is an analogous
background curator but for **skills only** (weekly, inactivity-triggered).

**Verdict: partially native** — turn-level auto-extraction/review is
native and on by default (the suite should simply not disable it in
rendered profiles, and should know cron-spawned agents skip it). Periodic
dreaming/consolidation is **not** native; if wanted, adopt the catalog
plugin or accept the gap — do not build a suite-side memory curator.

## Q13. Open-loop surfacing (unfinished business)

**Native detection — extensive, in the gateway dispatcher**
(`hermes_cli/kanban_db_dispatch.py`, run every tick):

- stale claims: claim TTL 15 min (`DEFAULT_CLAIM_TTL_SECONDS`), released
  and retried; heartbeat backstop 1 h even if the worker PID is alive;
- stale running: `kanban.dispatch_stale_timeout_seconds: 14400` (4 h) with
  a 1 h heartbeat gap → worker killed, run marked `stale`;
- crashed workers (PID/fingerprint checks), orphaned `running` rows
  reconciled (`kanban.reconcile_orphans: True`), max-runtime enforcement;
- **circuit breaker**: `kanban.failure_limit: 2` consecutive failures →
  card `blocked` + `gave_up` event; repeated same-kind blocks →
  `triage` + `block_loop_detected` event.

**Native diagnostics — rich but pull-only.** `hermes_cli/kanban_diagnostics.py`
rules: stuck-in-blocked (≥ `blocked_stale_hours`, default 24), block/unblock
cycling, stranded-in-ready (≥30 min, severity escalating), stale-running,
repeated failures/crashes, review deadlocks; thresholds under
`kanban.diagnostics.*`. Surfaced via `hermes kanban diagnostics` and the
dashboard. `board_stats()` gives per-status/per-assignee counts + oldest
ready age (`hermes kanban stats`). **No scheduled push of diagnostics or
any periodic board digest exists** (NOT FOUND); the dispatcher's own
distress signal is a throttled log warning, never a chat message. All
terminal-event escalation reaches humans **only through Q11's
subscriptions**.

**Verdict: partially native — build the push layer only.** Detection,
thresholds and severity already exist natively; the suite's reminder
ledger should consume `kanban_diagnostics` + `board_stats()` instead of
re-deriving staleness, and keep only what is genuinely suite-side:
scheduled delivery, dedupe fingerprints, and backoff (1 h → 24 h).

---

## Ranked verdicts for the three scoped questions

| Capability | Class | Basis |
|---|---|---|
| **Completion push** | **Partially native (build the gap only)** | Gateway/TUI/API origins: fully native auto-subscribe + notify+wake (Q11). Plain-CLI origin (the suite's primary entry today): natively silent; no home-channel fallback exists. Gap = subscribe a user chat at creation, or suite-tick delivery for unsubscribed cards. |
| **Memory dreaming** | **Partially native** | Turn-level background review + provider auto-extraction are native and automatic (Q12). Periodic consolidation/"dreaming": nothing in core; third-party catalog plugin only. |
| **Open-loop reminders** | **Partially native (build the push layer only)** | Detection/reclaim/circuit-breaking and a full diagnostics rule set are native (Q13); scheduled digest, dedupe and backoff are not. |

## Top adoption opportunities for superagent (ranked by impact)

1. **Seed a managed `SOUL.md` into every rendered profile** (Q1/Q8) —
   the Router's role behavior (Gate discipline, dispatch-only, report
   style) as the profile's identity file, with the Worker equivalent for
   workers. Directly fixes the observed failure: sa-router answering as
   a generic assistant because nothing guaranteed its role was in
   context. Static behavior belongs in SOUL, not in a skill the model
   may or may not open, and not in per-turn plugin injection.
2. **Pin role skills with `skills.auto_load`** in rendered `config.yaml`
   (Q3) — one line per profile turns the Router/Worker skills from
   "indexed, maybe opened" into guaranteed full-body context.
3. **Wire the chat entry natively: Feishu → sa-router via multiplexing**
   (Q5) — `gateway.multiplex_profiles` is already on; add a
   `gateway.profile_routes` entry (or a Feishu app in the router
   profile's own `.env`) in the installer and a doctor check for it.
   This also unlocks Q11's native completion push, because
   gateway-originated cards auto-subscribe with notify+wake.
4. **Close the CLI-origin notification gap in the suite tick** (Q11) —
   cards created from `hermes --profile sa-router` CLI chats are
   natively silent on completion. Shrink the suite's outbox/reminder
   machinery to exactly this: terminal events for cards with no
   `kanban_notify_subs` row. Everything with a subscriber is Hermes'
   job now.
5. **Rebuild reminders on native diagnostics** (Q13) — replace
   suite-side staleness logic with `kanban_diagnostics` rules +
   `board_stats()`; keep only scheduling, fingerprint dedupe and
   backoff in the suite.
6. **Use more of the card model in the Router skill** (Q4) — parent/child
   links for decomposed tasks (auto-promotion replaces suite-side
   dependency tracking), `kanban_attach` for deliverables (the gateway
   notifier uploads completed-card artifacts to the chat natively),
   `completion_contract` for acceptance checks.
7. **Offer Honcho as the optional cross-profile memory** (Q2) — one
   shared user peer across all suite profiles + one AI peer per role is
   exactly the "global memory" the suite's journal was approximating
   for user facts. Keep the journal for the task ledger (no native
   equivalent); don't build a suite memory store.
8. **Leave dreaming to native review + providers** (Q12) — ensure
   rendered profiles keep `memory.nudge_interval` and the background
   review enabled; if the operator wants periodic consolidation, point
   at the `hermes-dreaming` catalog plugin instead of growing a
   suite-side curator.
9. **Reserve plugin hooks for enforcement, not content** (Q8) — future
   Gate hardening has native fail-closed points (`pre_tool_call`,
   `pre_gateway_dispatch`) and kanban lifecycle hooks
   (`kanban_task_completed/blocked`) available; role *content* stays in
   SOUL.md/auto_load where it is cache-stable.

## UNVERIFIED / NOT FOUND register

- Kanban @mentions: NOT FOUND in schema, tools, or dashboard API.
- Kanban labels/tags: NOT FOUND (nearest: `tenant`, `project_id`).
- `custom_instructions` config key: NOT FOUND.
- Native global/shared scope for built-in memory: NOT FOUND.
- Kanban auto-delivery to a home/default channel for unsubscribed cards:
  NOT FOUND.
- Core periodic board digest or diagnostics push: NOT FOUND.
- Core memory "dreaming"/consolidation pass: NOT FOUND (catalog plugin only).
- Whole-profile runtime config inheritance key (`inherit`,
  `fallback_config`): NOT FOUND.
- Honcho/Mem0/Supermemory behavior is evidenced from in-repo docs,
  catalog manifests and core integration code (`hermes_cli/profiles_honcho.py`,
  `plugins/memory/config_schema.py`); those providers' plugin code itself
  is catalog-installed, not in-tree, so provider-internal behavior beyond
  the documented partition keys is UNVERIFIED at source level.
