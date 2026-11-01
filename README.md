# hermes-superagent

A Super-agent layer for [Hermes Agent](https://github.com/NousResearch/hermes-agent),
following the architecture explored in DeepSeek Harness team's
《Super-agent 设计探索：迈向更自主的 Agent 系统》 ("Super-agent design exploration: toward more autonomous agent systems") (Oct 2026):
a dispatch-only **Router**, Kanban-backed **Workers**, event **Fast Path**,
and an external **Watchdog** — so one human can supervise many concurrent
tasks instead of babysitting one session at a time.

> **Status: v0.12.2.** The dispatch chain is verified end-to-end on a
> live Hermes install (restricted Router → board → dispatcher →
> Worker → native completion). The suite is built from Hermes'
> own mechanisms wherever they exist, keeps no provider system of
> its own (roles select from your Hermes config; keys converge
> onto `~/.hermes/.env`), and adds the product layer around it —
> a transactional setup wizard, a recallable journal, a
> plain-language `doctor`, ledger-governed reminders, and
> one-command install / upgrade / uninstall. Product direction —
> Hermes-native, last-mile first, no pure-geek tooling — is
> binding: [docs/PRINCIPLES.md](docs/PRINCIPLES.md). Field
> lessons: [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).

## Quickstart

Requirements: Hermes (latest), installed and run at least once.
Linux (Ubuntu 24.04) and macOS.

### 1. Install — one line

```bash
curl -fsSL https://raw.githubusercontent.com/hezberg/hermes-superagent/main/bootstrap.sh | sh
```

This clones the suite into `~/.hermes/superagent/src` and runs the
installer once, laying down profiles, the board and the reminder
job with defaults: roles inherit the default profile's model,
keys converge from `~/.hermes/.env`. That is the machinery in
place — not yet your configuration. Step 2 is the other half of
a fresh install, not an optional extra.

Notes:
- Fresh Hermes with no model yet? Run `hermes setup` first — the
  suite builds on Hermes' own configuration, never replaces it.
- Nothing is left in your home directory; re-running the line
  updates the managed clone and re-converges.

### 2. Configure — run the wizard

```bash
hermes superagent setup
```

This is where the install becomes yours: worker topology (one
general worker by default; research/deep specialists are opt-in),
a provider and model per role — chosen from a list fetched live
from the provider's own endpoint — the Feishu chat entry, and a
delivery platform for reminders. Strict where it matters: one
Feishu app serves exactly one profile (a duplicate is a hard
stop, not a warning), and a binding that produced no app sends
you back into the step. The wizard is transactional: quit before
its commit point and nothing on disk changes. It ends by
offering the gateway restart; after that, the Router answers at
`hermes --profile sa-router` — and in Feishu, if you wired it.

Re-running the wizard reconfigures in place; everyday tweaks are
lighter still — `hermes superagent set-model <profile> <model>`,
or edit `~/.hermes/superagent/superagent.yaml` (edits apply
automatically, no reinstall).

Upgrades: `hermes superagent upgrade`. Uninstall:
`hermes superagent uninstall` (data kept unless `--purge`).

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

## Using it

**Give work.** Talk to the Router like a chief of staff:
`hermes --profile sa-router`, or in Feishu if you wired the
entry. Say what you want done — the Router decomposes it,
creates cards on the board and dispatches workers; it never does
the work itself. Big jobs become linked parent/child cards, and
every card carries its goal and completion contract with it.

**Watch progress.**
- In chat: `/board` — the suite's live board summary (what's
  running, blocked, just finished).
- The board itself, in the terminal: `hermes kanban list` —
  every card, its status and its assignee (Hermes' own board
  CLI; `hermes kanban` alone shows the other board verbs).
- The same board in a browser: `hermes dashboard` starts Hermes'
  web dashboard — the kanban board is one of its views, and the
  easiest way to read a busy board at a glance.
- `hermes superagent status`: the suite's own summary — profiles,
  board counts, recent journal.
- From Feishu there is nothing to poll: a card created from chat
  pushes its result back into the same conversation when it
  finishes. Cards dispatched from the CLI are covered by the
  reminder tick (every 10 minutes) — it reports completions and
  speaks up when work blocks, stalls, or finishes unreviewed,
  and stays silent when nothing changed.

**Recall what's been done.** Finished cards land in the journal,
which the Router (and you) can search: `hermes superagent digest`
for recent completions, `hermes superagent recall <keyword>` for
a specific one. Asking the Router "what happened with X?" works
too — finished work is its long-term memory.

**Steer or stop.** `/block <task-id>` in chat blocks a card
(`/board` shows the ids); plain language to the Router works as
well ("hold the research card until I say go").

**Look after it.** `hermes superagent doctor` — a plain-language
health check that names the fix, not just the fault. Change a
role's model with `hermes superagent set-model <profile> <model>`
(`hermes superagent providers` lists what your Hermes offers).

## Beyond the design article

DeepSeek's article (and their dsh prototype) supplies the
architecture and the Gate / Mandate / Report discipline. Everything
that makes it a product you can install — and leave alone — is
this suite's own work:

- **A full lifecycle, each step one command:** bootstrap install,
  `upgrade`, self-`uninstall`, generation snapshots with
  `--rollback` — and a setup wizard that is transactional
  (nothing on disk changes until it commits).
- **Configuration with a single source of truth:** roles select
  providers/models Hermes already has (no parallel system to
  maintain), keys converge onto `~/.hermes/.env`, edits apply
  automatically — no "now re-run the installer" step, ever.
- **Hermes-native adoption, researched at source level:** SOUL.md
  identities, auto-loaded role skills, per-profile memory seeds,
  native profile routing for chat entry, native completion
  subscriptions — with the reminder tick covering only the
  CLI-origin gap Hermes deliberately leaves.
- **Co-managed profiles:** renders never clobber what Hermes' own
  wizards wrote into a profile (your platform credentials survive
  every reconcile).
- **Memory and supervision for the operator:** the journal turns
  finished cards into recallable memory (`digest` / `recall`),
  reminders dedupe by fingerprint with backoff and stay silent
  when nothing changed, and `doctor` answers in plain language
  with the exact fix.
- **Guardrails at the seams:** duplicate Feishu apps hard-stop,
  empty bindings loop back, missing keys are diagnosed by their
  actual line state — not asserted.
- **221 unit tests** over the installer, renderer, wizard,
  journal, reminders and CLI, run on every release.

## Layout

| Path | What |
|---|---|
| `config/superagent.yaml` | The one configuration file (template with guidance) |
| `config/examples/` | Filled examples (DeepSeek) |
| `plugin/superagent/` | The Hermes plugin: `/board`, `/block`, `sa_status`, activity hooks, the setup wizard, and the `hermes superagent` CLI (status, doctor, journal / digest / recall, providers, set-model, setup, upgrade, uninstall) |
| `profiles/` | Router / worker profile templates (config, SOUL.md identity, memory seed, skills) rendered at install time |
| `scripts/` | The installer/uninstaller (`install.py` — one idempotent convergence for install, upgrade, repair, rollback), config validation, profile rendering, release helper |
| `bootstrap.sh` | The one-line first install (clones into `~/.hermes/superagent/src`, runs the installer) |
| `tests/` | Unit tests: `python3 -m unittest discover -s tests` |
| `hermes superagent setup` / `uninstall` | The guided install wizard / verified-clean self-uninstall (engines: `scripts/install.py`, `scripts/uninstall.py`) |
| `SETUP.md` | The agent-guided setup runbook (probe → questions → plan → execute → hand over) |
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
