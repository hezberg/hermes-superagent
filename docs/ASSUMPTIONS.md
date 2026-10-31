# Assumptions to verify at first live install

This suite was built against Hermes' published plugin/kanban
documentation without a live Hermes on the build machine. The following
points are isolated so each can be verified (and fixed) in exactly one
place when the suite meets a real installation:

1. **Profile config model keys** — templates render
   `model: {provider, default, base_url, api_key_env}` and the provider
   mapping in `scripts/render_profiles.py` (openai-compatible →
   `custom`, anthropic → `anthropic`). The `model.*` keys were
   confirmed in the field on 2026-11-01: Hermes' runtime reads
   `api_key_env` (its log names it `key_env`) and honours base_url and
   default model from the profile config.
2. **Toolset selection — RESOLVED (2026-11-01, official Kanban docs +
   field failure).** Toolsets do NOT live under `agent.toolsets`;
   v0.1/v0.2.0 rendered exactly that, and the result was a Router
   session with the full default toolset and no kanban tools at all.
   The real mechanism: per-platform selection under
   `platform_toolsets.<platform>` in the profile's config.yaml, or
   `hermes -p <profile> tools enable <toolset> [--platform <p>]`.
   Notes that matter:
   - `all` / `*` never enables `kanban`; it is deliberately opt-in.
   - A legacy top-level `toolsets:` is only a fallback when no platform
     selection was ever saved; `agent.disabled_toolsets` stays
     authoritative.
   - Dispatcher-spawned workers get the kanban lifecycle toolset
     force-added via the `HERMES_KANBAN_TASK` env flag, so worker
     profiles only list their work toolsets (renderer adds memory +
     skills).
   v0.2.1 templates write `platform_toolsets` and the installer also
   runs `hermes -p <router> tools enable kanban` as a second path.
3. **Plugin API signatures** — registration uses the documented
   `register(ctx)` surface (`register_tool`, `register_hook` with
   `on_session_start` / `on_session_end` / `post_tool_call`,
   `register_command`, `register_cli_command`, `register_skill`).
   Command handlers are written as `async def handler(ctx, args)` per the
   published tutorial; if your version passes a different shape, adapt
   `cmd_tasks` / `cmd_stop` in `plugin/superagent/__init__.py`.
4. **Skills location** — the installer copies the Router skill into
   `<router profile>/skills/router-superagent/` and the plugin also
   tries `register_skill` with the bundled copy. One of the two paths is
   enough; both are harmless.
5. **Cron** — watchdog scheduling is manual in v0.1.0 (see CONFIG.md).
   Automating it needs the target version's cron CLI, to be pinned down
   at first install.
6. **Board timestamps** — the watchdog reads `updated_at` /
   `last_heartbeat` (falling back to `heartbeat_at`) and accepts epoch
   numbers or ISO-8601 strings. If the board schema differs, adapt
   `board_tasks()` in the plugin; the detection logic itself is
   schema-free and unit-tested.
7. **Report derivation** — task stages are derived first from native
   board records: `board_events()` reads the board's event table (any
   table whose name contains "event", with task and type columns) and
   `derive_report()` maps run-concluding events (completed → ready,
   blocked → blocked, gave_up/crashed/timed_out → failed) and falls
   back to the task's status. `board_reports()` additionally scans a
   comment-like table for the optional `SA-REPORT:` upgrade. If your
   Hermes version stores events/comments elsewhere, adapt those two
   readers; derivation silently degrades to status-only.
8. **Gate enforcement point** — the Gate (`gate.py`) is pure logic. In
   v0.2 it is enforced by the Router skill (the Router runs the Gate
   before judging) and by the status surface; hard enforcement inside
   the gateway's message path is phase-2 work, once the live install
   shows where Hermes lets a plugin intercept inbound events.
9. **Field findings from the first live install (2026-11-01)** — three
   assumptions died on contact with a real machine and shaped v0.2.2:
   (a) *Skill loading is at the model's discretion.* A
   dispatcher-spawned worker completed its card through the native
   handoff (summary + artifacts) without ever loading the worker
   skill, so nothing in the suite may *depend* on a skill being read:
   reporting derives from native board records (item 7), and the
   worker skill only teaches the native discipline. (b) *Profiles do
   not inherit the default profile's config.* A global
   `security.allow_private_urls: true` left worker profiles still
   SSRF-blocked; settings the suite cares about are rendered into
   every profile (see CONFIG.md, security). (c) *Clash/mihomo fake-IP
   DNS makes every public hostname resolve into 198.18.0.0/15*, which
   Hermes' SSRF guard treats as internal — on such machines
   `allow_private_urls` is the difference between web tools working
   and not working at all.
10. **Chat-entry routing (unpinned).** The suite prepares everything
    on its side for a Feishu entry — the Router's rendered config
    carries `platform_toolsets.feishu: [kanban, memory, skills]`, the
    Router skill defines the completion wake-up protocol, SETUP.md §6
    lists the host steps. Two facts remain version-dependent and must
    be pinned on the target install: the exact platform key spelling
    (`feishu`) in toolset selection, and how a gateway chat is routed
    to a non-default profile (orchestrator_profile vs profile
    routes). Hermes' own docs establish the subscription half:
    cards created inside a gateway chat auto-subscribe their origin
    chat, and terminal events wake the creating agent
    (`kanban.auto_subscribe_on_create`, default on) — a bare CLI
    session has no deliverable destination, which is why completion
    notifications require the chat entry.
