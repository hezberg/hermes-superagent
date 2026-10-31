# Assumptions to verify at first live install

This suite was built against Hermes' published plugin/kanban
documentation without a live Hermes on the build machine. The following
points are isolated so each can be verified (and fixed) in exactly one
place when the suite meets a real installation:

1. **Profile config model keys** — templates render
   `model: {provider, default, base_url, api_key_env}` and
   `agent: {toolsets}`. If your Hermes version names these differently,
   fix the templates under `profiles/` and the `HERMES_PROVIDER` mapping
   in `scripts/render_profiles.py` (that mapping is the single place
   where provider types become Hermes provider values:
   openai-compatible → `custom`, anthropic → `anthropic`).
2. **Kanban availability** — the board is expected at
   `$HERMES_HOME/kanban.db` with a `tasks` table; the `kanban` toolset
   must be enabled for the Router profile and dispatcher-spawned workers
   (the wildcard `all` does not enable it). The plugin degrades
   gracefully (reports "not initialized") when the board is absent.
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
