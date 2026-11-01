# hermes-superagent

A Super-agent layer for [Hermes Agent](https://github.com/NousResearch/hermes-agent),
following the architecture explored in DeepSeek Harness team's
《Super-agent 设计探索：迈向更自主的 Agent 系统》 ("Super-agent design exploration: toward more autonomous agent systems") (Oct 2026):
a dispatch-only **Router**, Kanban-backed **Workers**, event **Fast Path**,
and an external **Watchdog** — so one human can supervise many concurrent
tasks instead of babysitting one session at a time.

> **Status: v0.12.0.** The dispatch chain is verified end-to-end on a
> live Hermes install (restricted Router → board → dispatcher →
> Worker → native completion). The suite is built from Hermes'
> own mechanisms wherever they exist: each profile's identity is
> its SOUL.md, role skills are auto-loaded into every session,
> profile memory is seeded once and then belongs to the agent,
> Feishu reaches the Router through native profile routing, and
> completion pushes ride Hermes' native subscriptions wherever
> they exist. It keeps no provider system of its own — each role
> *selects* a provider and model that already exist in your
> Hermes config (blank = inherit the default profile's model),
> and API keys live in one place, `~/.hermes/.env`, converged
> into every profile automatically. One guided wizard
> (`hermes superagent setup`) walks topology, per-role models —
> with the model list fetched live from the provider you pick —
> and the Feishu entry; it is transactional, so abandoning it
> midway changes nothing on disk. Underneath: a deterministic
> **Gate** in front of the Router's judgement, immutable
> **Mandates** on accepted tasks, `observe`/`auto` accept modes,
> a **journal** that turns finished work into recallable memory,
> a plain-language **`doctor`**, and a ledger-governed reminder
> tick that speaks only when unclosed work needs you.
> `hermes superagent uninstall` removes the suite itself.
> Product direction — Hermes-native, last-mile first, no
> pure-geek tooling — is binding: [docs/PRINCIPLES.md](docs/PRINCIPLES.md).
> Field lessons: [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).

## Why

Single-session agents cap out at the human's attention: one person can
follow roughly 3–5 active sessions. This suite restructures Hermes into
two layers — a resident Router that only talks, decomposes and dispatches,
and isolated Worker profiles that execute — with the Kanban board as the
durable handoff between them.

## Quickstart

Requirements: Hermes (latest) already installed and run at least once.
Nothing else — the suite runs on Hermes' own Python (it carries its
own YAML fallback; Hermes' Python has no PyYAML) and needs no extra
packages. Linux (Ubuntu 24.04) and macOS.

### Guided: the setup wizard

After the one-line install below, run:

```bash
hermes superagent setup
```

The wizard refuses to start until your default Hermes profile has a
model (it sends you to `hermes setup` first — the suite builds on
Hermes' own configuration, never replaces it), then walks you
through: worker topology (one general worker by default; research
and deep specialists are opt-in), a provider/model choice per role
— after you pick a provider it fetches that endpoint's live model
list for you to choose from — and an optional Feishu entry: paste
a new dedicated app's credentials, or bind through Hermes' own
setup (QR included). The Feishu rules are strict by design: one
app serves exactly one profile, a duplicate App ID is a hard
stop, and a binding that produced no Feishu app sends you back
into the step instead of waving you through. The whole wizard is
transactional — quit or Ctrl-C before its commit point and
nothing on disk changes. It finishes with kanban ready, reminder
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
nearly all: roles inherit its model setup by default, and each
profile's copy of the API key is converged onto the one value in
`~/.hermes/.env` automatically. One `hermes gateway restart`
and you can talk to the Router (`hermes --profile sa-router`).
To give a role a different provider or model, select from what
your Hermes already has — `hermes superagent set-model <profile>
<model>`, or edit `~/.hermes/superagent/superagent.yaml`; config
edits apply automatically on the next command, no reinstall.
Upgrades are simply `hermes superagent upgrade` — no checkout to
remember, anywhere.

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
| `plugin/superagent/` | The Hermes plugin: `/tasks`, `/stop`, `sa_status`, activity hooks, the setup wizard, and the `hermes superagent` CLI (status, doctor, journal / digest / recall, providers, set-model, setup, upgrade, uninstall) |
| `profiles/` | Router / worker profile templates (config, SOUL.md identity, memory seed, skills) rendered at install time |
| `scripts/` | The installer/uninstaller (`install.py` — one idempotent convergence for install, upgrade, repair, rollback), config validation, profile rendering, release helper |
| `bootstrap.sh` | The one-line first install (clones into `~/.hermes/superagent/src`, runs the installer) |
| `tests/` | Unit tests: `python3 -m unittest discover -s tests` |
| `hermes superagent setup` / `uninstall` | The guided install wizard / verified-clean self-uninstall (engines: `scripts/install.py`, `scripts/uninstall.py`) |
| `SETUP.md` | The agent-guided setup runbook (probe → questions → plan → execute → hand over) |
| `INSTALL_PROMPT.md` | The paste-ready prompt that hands the setup to your Hermes |
| `docs/` | Architecture mapping, config reference, assumptions, product principles |

## Design notes

- **No parallel provider system.** The suite defines no providers
  of its own: each role selects a provider + model that already
  exist in your Hermes configuration (both blank = inherit the
  default profile's model), rendered exactly the way Hermes seeds
  them itself. Keys live only in `~/.hermes/.env`; profile copies
  are converged onto that single source of truth automatically —
  change the key once, everywhere follows.
- **Hermes-native wherever Hermes has the mechanism.** Identity
  is each profile's SOUL.md (the Router's says: dispatch first,
  don't ask permission to create a card); role skills are
  auto-loaded into every session; each profile's memory is seeded
  once at install and is the agent's own file after that; chat
  entry uses Hermes' native profile routing; completion pushes
  use native gateway subscriptions, and the suite's reminder tick
  covers only the gap Hermes deliberately leaves (cards created
  from the plain CLI).
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
- **Installs are reversible.** Everything the installer creates is
  recorded in the install state (`state.json`); each install
  snapshots the previous generation first
  (`python3 scripts/install.py --rollback` restores it), and
  `hermes superagent uninstall` removes exactly the recorded
  files and verifies — your own data (.env, sessions, memory,
  journal, config) survives unless you pass `--purge`.

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
