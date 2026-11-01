# hermes-superagent

A Super-agent layer for [Hermes Agent](https://github.com/NousResearch/hermes-agent),
following the architecture explored in DeepSeek Harness team's
《Super-agent 设计探索：迈向更自主的 Agent 系统》 (Oct 2026):
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

请帮我安装并配置 hermes-superagent，全程按它仓库里的 SETUP.md 执行：

1. 先跑引导安装（源码会落在 Hermes 自己的目录里，不要往我的主目录克隆任何东西）：`curl -fsSL https://raw.githubusercontent.com/hezberg/hermes-superagent/main/bootstrap.sh | sh`。它会生成配置文件并停下，仓库在 `~/.hermes/superagent/src`，需要读 SETUP.md 就去那里读。
2. 完整读一遍 SETUP.md，按它走：先探查、再逐个问我问题（一个问题一条消息、带上你的推荐答案）、把计划汇总成一条消息让我确认，确认后才动手。
3. 硬规则：
   - 绝不要让我在聊天里发 API key，也不要读取、打印或保存任何 key 的值。到需要 key 时，给我确切的一行（`<变量名>=<key>`，写进 `~/.hermes/.env`），我自己在终端完成，你只确认变量名已就位。
   - 配置这样来：首选跑向导 `hermes superagent setup`（未装时从仓库跑 `python3 scripts/install.py --wizard`）让我逐项选；要手写配置的话，先跑一次 `python3 scripts/install.py`，它会在 ~/.hermes/superagent/superagent.yaml 生成配置文件并停下，把你问到的答案写进那份文件（先给我看一遍再写入），然后再跑一次装完。不要手改 `~/.hermes/profiles/` 下渲染出的任何文件；仓库里不要留任何我的配置。
   - 如果你正运行在 gateway 对话里，重启 gateway 前先提醒我对话会中断，并把重启放在最后一步。
4. 完成标准，逐项核对后才算完：安装成功；`hermes superagent status` 可用；`hermes superagent doctor` 没有任何 ✗；最后用 sa-router 试跑一个小任务，看板上有卡且能跑完。
5. 提醒投递：装完问我未闭环提醒发到哪个平台，帮我把 cron 任务的 `--deliver` 指过去；我说以后再定的话，跳过并在交接里写清补法。
6. 全部完成以后，用一段人话向我交接：怎么派活、在哪看进度、怎么卸载。

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
