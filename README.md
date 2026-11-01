# hermes-superagent

A Super-agent layer for [Hermes Agent](https://github.com/NousResearch/hermes-agent),
following the architecture explored in DeepSeek Harness team's
《Super-agent 设计探索：迈向更自主的 Agent 系统》 ("Super-agent design exploration: toward more autonomous agent systems") (Oct 2026):
a dispatch-only **Router**, Kanban-backed **Workers**, event **Fast Path**,
and an external **Watchdog** — so one human can supervise many concurrent
tasks instead of babysitting one session at a time.

> **Status: v0.12.0.** The dispatch chain is verified end-to-end on a
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
> v0.3 adds the **journal** (finished work becomes recallable global
> memory) and a plain-language **`doctor`**; v0.4 adds **proactive
> reminders** for unclosed work — a ledger-governed cron tick that
> speaks only when a blocked, stalled, or unreviewed task needs you.

## Why

Single-session agents cap out at the human's attention: one person can
follow roughly 3–5 active sessions. This suite restructures Hermes into
two layers — a resident Router that only talks, decomposes and dispatches,
and isolated Worker profiles that execute — with the Kanban board as the
durable handoff between them.

## Quickstart

Requirements: Hermes (latest) already installed and run at least once,
Python 3 with PyYAML (ships with Hermes). Linux (Ubuntu 24.04) and macOS.

### Guided: the setup wizard

After the one-line install below, run:

```bash
hermes superagent setup
```

The wizard refuses to start until your default Hermes profile has a
model (it sends you to `hermes setup` first — the suite builds on
Hermes' own configuration, never replaces it), then walks you
through: worker topology (one worker, or specialists too), a
provider/model choice per role, and an optional Feishu entry — paste
a new dedicated app's credentials (it checks the App ID is not
already used by another profile; one app serves one profile) or bind
through Hermes' own setup. It finishes with kanban ready, reminder
delivery set, and a doctor verdict. Re-running it reconfigures in
place.

### Recommended: one line, nothing left in your home directory

```bash
curl -fsSL https://raw.githubusercontent.com/hezberg/hermes-superagent/main/bootstrap.sh | sh
```

The bootstrap keeps the suite's source inside Hermes' own directory
(`~/.hermes/superagent/src` — the plugin, profiles, config, and
history all live under `~/.hermes/` too) and runs the installer. If
your default Hermes profile already talks to a model, that is
nearly all: roles inherit its model setup, and the installer syncs
the API key into each profile itself. One `hermes gateway restart`
and you can talk to the Router (`hermes --profile sa-router`).
Edit `~/.hermes/superagent/superagent.yaml` only to select a
*different* provider or model for a role. Upgrades are simply
`hermes superagent upgrade` — no checkout to remember, anywhere.

### Or: let Hermes install it for you

Open a chat with your stock Hermes (default profile, CLI or Desktop)
and paste the prompt below — also saved as
[INSTALL_PROMPT.md](INSTALL_PROMPT.md). Hermes follows
[SETUP.md](SETUP.md): it probes your install, asks a few questions one
at a time (each with a recommended answer), shows you a plan, and only
then installs. **The one step that stays with you is entering your API
key** — in your own terminal, into `~/.hermes/.env`, never in the chat.

<details>
<summary>Install prompt (click to expand)</summary>

Please install and configure hermes-superagent for me, following the SETUP.md in its repo throughout:

1. Start with the guided install (the source must land inside Hermes' own directory — do not clone anything into my home directory): `curl -fsSL https://raw.githubusercontent.com/hezberg/hermes-superagent/main/bootstrap.sh | sh`. It generates the config file and stops; the repo lives at `~/.hermes/superagent/src` — read SETUP.md there.
2. Read SETUP.md in full and follow it: probe the environment first, then ask me the questions one at a time (one question per message, each with your recommended answer), then summarize the plan in a single message for my confirmation — only start once I confirm.
3. Hard rules:
   - Never ask me to send an API key in chat, and never read, print or store any key value. When a key is needed, give me the exact line (`<VAR_NAME>=<key>`, to go into `~/.hermes/.env`); I will do it in my own terminal — you only verify the variable name is in place.
   - Configuration: prefer the wizard, `hermes superagent setup` (before the suite is installed, run `python3 scripts/install.py --wizard` from the repo), letting me pick each option. If writing the config by hand instead: run `python3 scripts/install.py` once — it generates ~/.hermes/superagent/superagent.yaml and stops; write the answers I gave into that file (show me before writing), then run it once more to finish the install. Never hand-edit any rendered file under `~/.hermes/profiles/`, and never leave any of my config in the repo tree.
   - If you are running inside a gateway conversation, warn me before restarting the gateway that the conversation will drop, and make the restart the very last step.
4. Done means every item checks out: the install succeeded; `hermes superagent status` works; `hermes superagent doctor` shows no ✗ at all; finally, run a small test task through sa-router and confirm a card lands on the board and completes.
5. Reminder delivery: after the install, ask me which platform the unfinished-work reminders should be delivered to, and point the cron job's `--deliver` there; if I say I'll decide later, skip it and write the fix-up steps into the handover.
6. When everything is done, hand over in plain language: how I dispatch work, where I watch progress, and how I uninstall.

</details>

### Manual install (from a checkout — for development)

```bash
git clone https://github.com/hezberg/hermes-superagent.git
cd hermes-superagent

# Guided install from the checkout (the wizard writes your config
# for you; user values live ONLY at ~/.hermes/superagent/, never in
# the repo tree, so git pull can never conflict over them):
python3 scripts/install.py --wizard

# …or by hand, in two runs: the first generates
# ~/.hermes/superagent/superagent.yaml and stops; fill it in, then
# run again to install (later runs upgrade / repair — one
# idempotent convergence; the previous generation is snapshotted
# first, and `python3 scripts/install.py --rollback` restores it):
python3 scripts/install.py
$EDITOR ~/.hermes/superagent/superagent.yaml
python3 scripts/install.py

# Keys — never in the yaml; the config names an env var. Add one
# line to ~/.hermes/.env, then restart the gateway. Talk to the
# Router from the Hermes CLI and give it a task:
hermes --profile sa-router
```

Uninstall (removes exactly what the install state recorded; your
config and history are kept unless you pass `--purge`):

```bash
hermes superagent uninstall          # add --purge to remove data too
```

Upgrading later does not need the checkout at all — the installed
suite upgrades itself (it records where its source lives, and keeps
its own clone if that is ever lost):

```bash
hermes superagent upgrade
```

## Layout

| Path | What |
|---|---|
| `config/superagent.yaml` | The one configuration file (template with guidance) |
| `config/examples/` | Filled examples (DeepSeek) |
| `plugin/superagent/` | The Hermes plugin: `/tasks`, `/stop`, `sa_status`, activity hooks, `hermes superagent` CLI, bundled Router skill |
| `profiles/` | Router / worker profile templates rendered at install time |
| `scripts/` | The installer/uninstaller (`install.py` — one idempotent convergence for install, upgrade, repair, rollback), config validation, profile rendering, release helper |
| `tests/` | Unit tests: `python3 -m unittest discover -s tests` |
| `hermes superagent setup` / `uninstall` | The guided install wizard / verified-clean self-uninstall (engines: `scripts/install.py`, `scripts/uninstall.py`) |
| `SETUP.md` | The agent-guided setup runbook (probe → questions → plan → execute → hand over) |
| `INSTALL_PROMPT.md` | The paste-ready prompt that hands the setup to your Hermes |
| `docs/` | Architecture mapping, config reference, assumptions, product principles |

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

- DeepSeek Harness team, 《Super-agent 设计探索：迈向更自主的 Agent 系统》 ("Super-agent design exploration: toward more autonomous agent systems")
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
