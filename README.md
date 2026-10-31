# hermes-superagent

A Super-agent layer for [Hermes Agent](https://github.com/NousResearch/hermes-agent),
following the architecture explored in DeepSeek Harness team's
《Super-agent 设计探索：迈向更自主的 Agent 系统》 (Oct 2026):
a dispatch-only **Router**, Kanban-backed **Workers**, event **Fast Path**,
and an external **Watchdog** — so one human can supervise many concurrent
tasks instead of babysitting one session at a time.

> **Status: v0.3.0.** The dispatch chain is verified end-to-end on a
> live Hermes install (restricted Router → board → dispatcher →
> Worker → native completion). On top of the v0.1 skeleton (layout,
> configuration system, plugin registration, profile rendering,
> install/uninstall cycle, unit-tested pure logic), v0.2 adds the
> authorization layer adapted from DeepSeek's own prototype: a
> deterministic **Gate** in front of the Router's judgement, immutable
> **Mandates** on accepted tasks, `observe`/`auto` accept modes,
> board-derived task stages, and an agent-guided [SETUP.md](SETUP.md).
> Field lessons from the first live install are recorded in
> [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md) item 9; the product
> direction — Hermes-native, last-mile first, no pure-geek tooling —
> is binding and written down in [docs/PRINCIPLES.md](docs/PRINCIPLES.md).

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
- **Authorization precedes judgement.** A deterministic Gate checks the
  sender against per-source allowed lists before any model sees the
  request; every accepted task records an immutable Mandate (policy
  version, scope, strength). Proactive work starts in `observe` mode:
  recorded, never executed, until the operator switches to `auto`.
- **Worker state is derived from the board's own records** — the
  native completion summary, block events and heartbeats — with an
  optional structured enum (`SA-REPORT: ready|blocked|…`) as an
  upgrade when a worker provides one. The Watchdog reasons over facts
  either way; timestamp stall detection is the fallback.
- **Watchdog defaults to report-only.** It surfaces stalled tasks; acting
  on them (nudge / requeue) is an explicit opt-in in the config.
- **Installs are reversible.** Everything the installer creates is listed
  in a manifest; uninstall removes exactly that list and verifies.

## Design references

- DeepSeek Harness team, 《Super-agent 设计探索：迈向更自主的 Agent 系统》
  (Oct 2026) — the architecture this suite follows.
- [deepseek-ai/dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype)
  — DeepSeek's own research prototype for their Harness. The Gate /
  Mandate / accept-mode design, the Report taxonomy, the store-first
  Outbox discipline and the agent-guided SETUP pattern are adapted from
  it (MIT). Its scope — one GitHub repository, DSH sessions — differs
  from this suite's (general dispatch on Hermes); mechanisms were
  borrowed, not the codebase.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the five modules
of the original design map onto Hermes, including the one module that is
only partially achievable from outside Hermes core.

## License

MIT — see [LICENSE](LICENSE).
