# SETUP

Instructions for an agent that sets up hermes-superagent with its
operator. If you are a person, ask your coding agent to read this file
and follow it. (Pattern borrowed from DeepSeek's dsh-superagent
prototype, whose setup works the same way — for the same reason: setup
should cost as little of the operator's attention as possible.)

## How to run the setup

- **Probe first, ask second.** Run the probe below once and keep the
  result to yourself. Skip every question the probe already answers.
- **Ask one question per message**, about one thing, each with a
  recommended answer the operator can accept in one word and one
  sentence on why it matters.
- **Do not execute while asking.** Collect the answers, send one short
  message with the full plan, and install only after the operator
  confirms it.
- **Never ask for a secret in the chat.** API keys are entered by the
  operator in their own terminal (step 4 below). You handle everything
  that is not a secret.

## 1. Probe

Run from this checkout, once:

```sh
command -v hermes && hermes --version
python3 --version
ls -d "${HERMES_HOME:-$HOME/.hermes}" 2>/dev/null
ls "${HERMES_HOME:-$HOME/.hermes}"/plugins 2>/dev/null
ls "${HERMES_HOME:-$HOME/.hermes}"/profiles 2>/dev/null
```

Missing `hermes` is a plan item, not a question: hermes-superagent is an
add-on and does not install Hermes itself. Existing `sa-*` profiles mean
an earlier install — read its manifest
(`$HERMES_HOME/superagent/manifest.json`) and ask whether to upgrade in
place (re-run `install.sh --force`) before changing anything.

## 2. Questions

Ask in this order, one per message. Recommendations in brackets.

1. **Provider.** Which endpoint should the suite call? Both API shapes
   are wired: OpenAI-compatible (OpenAI, DeepSeek, OpenRouter, a local
   server, ...) or Anthropic. [Whichever you already have a key for.]
2. **Base URL.** The endpoint root for that provider. [The provider's
   public API root; a gateway URL if you run one.]
3. **Models.** One per role — Router, general worker, research worker,
   deep worker; the same model may serve several roles. [Router: your
   fastest cheap model — it routes, it does not grind. Deep worker:
   your strongest or a reasoning model, if you have one.]
4. **Sources.** Besides the CLI, should anything else be allowed to ask
   for work — Feishu, webhooks? For each: which identities may ask?
   [CLI only to start; widen once the behaviour looks right. Identities
   are per-source and are never mapped to each other.]
5. **Accept mode.** `observe` records what the agent *would* dispatch
   without running it; `auto` also lets rule-matched candidates become
   real work. [observe — explicit requests from allowed senders work
   either way; only unasked work is held back.]
6. **Reminder delivery.** The suite can proactively message the
   operator when work blocks, stalls, or finishes unreviewed. Which
   connected platform should those reminders go to? [Whichever chat
   you actually read — e.g. Feishu. "Later" is a fine answer; the
   ledger still records everything, and the target can be set any
   time with `hermes cron edit <id> --deliver <platform>`.]

Do not ask about values with a good default; list them in the plan:
watchdog report-only with 30-minute stall threshold, one worker slot
reserved for human follow-ups, Router plus three workers with the
default profile names.

## 3. Plan

One short message: the config you will write (provider, base URL,
models, sources, accept mode), the install command, and the one
operator step (entering keys). Ask for one confirmation.

## 4. Execute

1. **Install.** Run `./install.sh` once. With no config anywhere it
   writes the guided template to
   `~/.hermes/superagent/superagent.yaml` — that file is the only
   place user values ever live; the repo tree stays clean, so
   `git pull` can never conflict over it. **If the default Hermes
   profile already has a model configured, the install proceeds in
   the same run**: every role left model-less inherits the default
   profile's model block verbatim. Only when there is nothing to
   inherit does the installer stop and ask for values.
2. Optionally write selections into that file (a different provider
   or model for a role — names from your Hermes config only;
   `hermes superagent providers` lists them). Validate:
   `python3 scripts/validate_config.py ~/.hermes/superagent/superagent.yaml`
   — fix every ERROR before continuing. (A filled staging file may
   still be passed once via `--config` to seed the suite config;
   after that it is ignored, by design.) **Later edits apply
   themselves**: the next `hermes superagent` command — or the
   reminder tick, within one cycle — re-renders the profiles; there
   is no separate apply step to remember. For a model change
   specifically, one command does the edit and the apply:
   `hermes superagent set-model sa-worker-deep <model-name>`
   (`inherit` as the name clears the override).
3. **Operator step — the only one that must happen outside the
   agent.** Send one message with the exact line(s) for the operator
   to add to `~/.hermes/.env` in their own editor or terminal, one
   per provider: `<api_key_env name>=<the key itself>`. Never
   receive, print, or store the value yourself; ask only for
   confirmation that the line exists. **The installer syncs the key
   from the global `.env` into each profile's `.env` by itself** —
   nobody copies keys between profiles by hand. The global `.env`
   is the single source of truth for keys: rotating a key later is
   editing that one line, and the profiles converge onto it
   automatically (next superagent command, or within one reminder
   tick). Then the gateways
   need a restart to pick it up — if you are running inside a
   gateway chat, warn the operator the conversation will drop and
   resume, and make the restart your last step.
4. Install: `./install.sh` (same command as phase one — install,
   upgrade, and repair are one idempotent convergence). It snapshots
   the previous generation first (rollback: `./install.sh --rollback`),
   and refuses nothing silently: a refusal names the validation
   problem; fix that, not around it.
5. Verify: start the profile gateways per docs/CONFIG.md, then check
   `hermes superagent status` — config loaded, profiles listed, board
   present — and run `hermes superagent doctor`: it checks the whole
   install (keys, toolsets, fake-IP DNS, rendered configs) and reports
   in prose with fixes. Clear every ✗ before handing over.
6. Reminder delivery: if the operator picked a platform in question
   6, point the tick's cron job at it — `hermes cron list` to find
   the job, then `hermes cron edit <id> --deliver <platform>`. If
   they said "later", leave it and note the same command in the
   hand-over.
7. Smoke test: give the Router one small real task and watch its card
   complete on the board before handing over. A setup that never ran
   a task is not a finished setup.

## 5. Hand over

One short message:

- How to try it: from the CLI, give the Router one small real task and
  watch the card appear on the board (`/tasks` shows the summary).
- The three operator rules: start narrow (few allowed senders, observe
  mode), tune for less noise, and read what the agent sends in your
  name — you own it.
- Where to read more: README.md, then docs/CONFIG.md and
  docs/ARCHITECTURE.md.
- How to undo everything: `./uninstall.sh`.

## 6. Optional: chat entry (Feishu)

The CLI proves the chain; the chat entry is what makes it a product
(docs/PRINCIPLES.md: tasks should start in the chat the operator
already lives in, and completion should arrive unasked). Wire it once
the CLI path works:

1. The default profile's gateway must already be connected to Feishu
   (check its status first; connecting it is an operator step).
2. Point board orchestration at the Router:
   `hermes config set kanban.orchestrator_profile <router profile>`.
3. The Router's rendered config already enables `kanban` for the
   `feishu` platform (`platform_toolsets.feishu`), and the installer
   also tries `hermes -p <router> tools enable kanban --platform
   feishu`. Confirm with `hermes -p <router> tools list` if available.
4. Allowlists, both layers: the operator's Feishu identity (open_id)
   goes into `policy.sources.feishu.allowed_senders` in the suite
   config, AND the gateway's own sender policy must let that identity
   through (a fresh gateway denies unknown senders by default — its
   startup log says so when no allowlists are configured).
5. Test from Feishu with one small task. Expected: the Router creates
   a card instead of doing the work; when the card finishes, a message
   returns to the same conversation and the Router reports the outcome
   itself (Hermes auto-subscribes chat-created cards by default —
   `kanban.auto_subscribe_on_create`).

Version-dependent step: how a gateway chat is routed to a non-default
profile differs across Hermes versions. If the Feishu conversation is
answered by the default profile instead of the Router, do not improvise
a workaround — record the exact behaviour and report it; routing is
pinned per target version in docs/ASSUMPTIONS.md item 10.
