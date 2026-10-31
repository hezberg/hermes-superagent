# hermes-superagent

A Super-agent layer for [Hermes Agent](https://github.com/NousResearch/hermes-agent),
following the architecture explored in DeepSeek Harness team's
《Super-agent 设计探索：迈向更自主的 Agent 系统》 (Oct 2026):
a dispatch-only **Router**, Kanban-backed **Workers**, event **Fast Path**,
and an external **Watchdog** — so one human can supervise many concurrent
tasks instead of babysitting one session at a time.

> **Status: v0.1.0 — CLI skeleton.** The repository layout, configuration
> system, plugin registration, profile rendering, install/uninstall cycle
> and the pure decision logic (Fast Path, Watchdog stall detection) are in
> place and unit-tested. End-to-end dispatch on a live Hermes install is
> the next milestone. Design choices that depend on the exact Hermes
> version are listed in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).

## Why

Single-session agents cap out at the human's attention: one person can
follow roughly 3–5 active sessions. This suite restructures Hermes into
two layers — a resident Router that only talks, decomposes and dispatches,
and isolated Worker profiles that execute — with the Kanban board as the
durable handoff between them.

## Quickstart

Requirements: Hermes (latest) already installed and run at least once,
Python 3 with PyYAML (ships with Hermes). Linux (Ubuntu 24.04) and macOS.

```bash
git clone https://github.com/hezberg/hermes-superagent.git
cd hermes-superagent

# 1. Configure: one file. Providers (OpenAI-compatible and Anthropic
#    endpoints are both wired), models per role, watchdog behaviour.
cp config/examples/deepseek.yaml config/superagent.yaml   # or edit the template
$EDITOR config/superagent.yaml

# 2. Install (additive only; refuses to overwrite anything silently)
./install.sh

# 3. Provide keys — never in the yaml; the config names an env var
export SUPERAGENT_MAIN_API_KEY=...   # use your provider's key

# 4. Start the router + worker profile gateways, then talk to the Router
#    from the Hermes CLI and give it a task.
```

Uninstall (removes exactly what the install manifest recorded):

```bash
./uninstall.sh
```

## Layout

| Path | What |
|---|---|
| `config/superagent.yaml` | The one configuration file (template with guidance) |
| `config/examples/` | Filled examples (DeepSeek) |
| `plugin/superagent/` | The Hermes plugin: `/tasks`, `/stop`, `sa_status`, activity hooks, `hermes superagent` CLI, bundled Router skill |
| `profiles/` | Router / worker profile templates rendered at install time |
| `scripts/` | Config validation and profile rendering |
| `tests/` | Unit tests: `python3 -m unittest discover -s tests` |
| `install.sh` / `uninstall.sh` | One-click install / verified-clean uninstall |
| `docs/` | Architecture mapping, config reference, assumptions |

## Design notes

- **Providers are user-configured.** Both OpenAI-compatible and Anthropic
  API shapes are supported; which model each role runs is a config value,
  never hard-coded. Keys live only in environment variables.
- **The Router cannot do the work itself** — its profile ships without
  execution toolsets. Dispatching is enforced by capability, not by hope.
- **Watchdog defaults to report-only.** It surfaces stalled tasks; acting
  on them (nudge / requeue) is an explicit opt-in in the config.
- **Installs are reversible.** Everything the installer creates is listed
  in a manifest; uninstall removes exactly that list and verifies.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the five modules
of the original design map onto Hermes, including the one module that is
only partially achievable from outside Hermes core.

## License

MIT — see [LICENSE](LICENSE).
