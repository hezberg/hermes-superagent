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
an earlier install — read its state
(`$HERMES_HOME/superagent/state.json`) and ask whether to upgrade in
place (re-run the installer: `python3 scripts/install.py`) before changing anything.

Two probe results decide whole branches, so get them now:

- **Does the default profile have a model?** Read the `model:` block of
  `$HERMES_HOME/config.yaml`. If there is none, the suite has nothing
  to build on: the operator runs `hermes setup` first — that is a plan
  item, not something you improvise around.
- **Which providers/models exist in Hermes?** `hermes superagent
  providers` (after install) — or read `providers:` /
  `custom_providers:` in the same config.yaml. These names are the
  ONLY things a role may select; the suite defines no providers of
  its own.

## 2. Questions

Ask in this order, one per message. Recommendations in brackets.

1. **Models per role.** For each role — Router, general worker, and
   any specialists — pick from the providers/models that already
   exist in the operator's Hermes (the probe listed them), or leave
   the role blank to inherit the default profile's model. Never ask
   for endpoints, base URLs or new provider definitions: there is
   nothing to define. [Inherit everywhere to start; specialize a
   role only when the operator names a model for it. Router: it
   routes, it does not grind.]
2. **Sources.** Besides the CLI, should anything else be allowed to ask
   for work — Feishu, webhooks? For each: which identities may ask?
   [CLI only to start; widen once the behaviour looks right. Identities
   are per-source and are never mapped to each other.]
3. **Accept mode.** `observe` records what the agent *would* dispatch
   without running it; `auto` also lets rule-matched candidates become
   real work. [observe — explicit requests from allowed senders work
   either way; only unasked work is held back.]
4. **Reminder delivery.** The suite can proactively message the
   operator when work blocks, stalls, or finishes unreviewed. Which
   connected platform should those reminders go to? [Whichever chat
   you actually read — e.g. Feishu. "Later" is a fine answer; the
   ledger still records everything, and the target can be set any
   time with `hermes cron edit <id> --deliver <platform>`.]

Do not ask about values with a good default; list them in the plan:
watchdog report-only with 30-minute stall threshold, one worker slot
reserved for human follow-ups, Router plus ONE worker (general) with
the default profile names — specialist workers (research, deep) are
opt-in config blocks, added only when the operator wants them.

## 3. Plan

One short message: the config you will write (per-role model
selections, sources, accept mode), the install command, and the
operator steps, if any (entering a key; the Feishu app, see §6).
Ask for one confirmation.

## 4. Execute

1. **Install.** Run `python3 scripts/install.py` once. With no config anywhere it
   writes the guided template to
   `~/.hermes/superagent/superagent.yaml` — that file is the only
   place user values ever live; the repo tree stays clean, so
   `git pull` can never conflict over it. **If the default Hermes
   profile already has a model configured, the install proceeds in
   the same run**: every role left model-less inherits the default
   profile's model block verbatim. Only when there is nothing to
   inherit does the installer stop and ask for values. (The
   interactive wizard, `hermes superagent setup`, is the operator's
   own terminal tool — you cannot drive it from a chat; your path
   is this file: answers in chat, config written by you, installer
   run by you.)
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
4. Re-run `python3 scripts/install.py` after writing the config
   (install, upgrade, and repair are one idempotent convergence).
   It snapshots the previous generation first (rollback: `python3 scripts/install.py --rollback`),
   and refuses nothing silently: a refusal names the validation
   problem; fix that, not around it.
5. Verify: run `hermes superagent status` — config loaded, profiles
   listed, board present — and `hermes superagent doctor`: it checks
   the whole install (keys converged, toolsets, rendered configs,
   entry wiring) and reports in prose with fixes. Clear every ✗
   before handing over.
6. Reminder delivery: if the operator picked a platform in question
   4, point the tick's cron job at it — `hermes cron list` to find
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
- How to undo everything: `hermes superagent uninstall`.

## 6. Optional: chat entry (Feishu)

The CLI proves the chain; the chat entry is what makes it a product
(docs/PRINCIPLES.md: tasks should start in the chat the operator
already lives in, and completion should arrive unasked). Wire it
once the CLI path works.

**The one hard rule: one Feishu app serves exactly one profile.**
Two profiles bound to the same app fight over its event stream —
silently, and it looks like random message loss. Everything below
follows from that.

- **Never touch the app that carries the current conversation.**
  If you are talking to the operator through the default profile's
  Feishu app, that app stays with the default profile. Do not move
  it, rebind it, or copy its credentials into the Router's profile.
  The Router needs a separate app of its own; if the operator has
  no second app, stop here, skip the entry, and say exactly that
  in the hand-over.
- **Preferred path — the operator's terminal:** tell the operator
  to run `hermes superagent setup` and choose the Feishu step
  there. The wizard enforces the hard rule itself: it scans every
  profile for App ID conflicts and hard-stops on a duplicate, and
  a binding that produced no app sends them back into the step.
- **By hand (only with a dedicated app for the Router):** put the
  app's `FEISHU_APP_ID` / `FEISHU_APP_SECRET` in the Router
  profile's own `.env`, and record `entry: {platform: feishu}` in
  `superagent.yaml`. `hermes superagent doctor` verifies the
  wiring and prints the exact fix when it is missing. (Routing is
  native: a profile with its own platform credentials is served
  by the multiplexed gateway; `gateway.profile_routes` in the
  default profile is the alternative — see docs/ASSUMPTIONS.md
  item 10, resolved.)
- Allowlists, both layers: the operator's Feishu identity (open_id)
  goes into `policy.sources.feishu.allowed_senders` in the suite
  config, AND the gateway's own sender policy must let that
  identity through (a fresh gateway denies unknown senders by
  default — its startup log says so when no allowlists are
  configured).
- Test from Feishu with one small task. Expected: the Router
  creates a card instead of doing the work; when the card
  finishes, a message returns to the same conversation and the
  Router reports the outcome itself (Hermes auto-subscribes
  chat-created cards by default — `kanban.auto_subscribe_on_create`).
