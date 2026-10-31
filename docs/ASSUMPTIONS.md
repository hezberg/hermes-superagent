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
7. **Report comments** — the stage derivation reads worker reports from
   a comment-like table on the board (any table whose name contains
   "comment", with task and body columns) and parses the `SA-REPORT:`
   first line. If your Hermes version stores comments elsewhere, adapt
   `board_reports()`; stages silently fall back to status-only when no
   reports are found.
8. **Gate enforcement point** — the Gate (`gate.py`) is pure logic. In
   v0.2 it is enforced by the Router skill (the Router runs the Gate
   before judging) and by the status surface; hard enforcement inside
   the gateway's message path is phase-2 work, once the live install
   shows where Hermes lets a plugin intercept inbound events.
