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

Do not ask about values with a good default; list them in the plan:
watchdog report-only with 30-minute stall threshold, one worker slot
reserved for human follow-ups, Router plus three workers with the
default profile names.

## 3. Plan

One short message: the config you will write (provider, base URL,
models, sources, accept mode), the install command, and the one
operator step (entering keys). Ask for one confirmation.

## 4. Execute

1. Write the answers into `config/superagent.yaml` (or copy the closest
   file from `config/examples/` and edit it). Validate:
   `python3 scripts/validate_config.py config/superagent.yaml` — fix
   every ERROR before continuing; warnings about empty fields mean an
   answer is still missing.
2. **Operator step.** Send one message with the exact commands for the
   operator to run in their own terminal to export the key(s) — the
   variable names come from `api_key_env` in the config, e.g.
   `export SUPERAGENT_MAIN_API_KEY=...`. Wait for their confirmation.
   Never receive, print, or store the key yourself.
3. Install: `./install.sh --config config/superagent.yaml`. A refusal
   names the collision or validation problem; fix that, not around it.
4. Verify: start the profile gateways per docs/CONFIG.md, then check
   `hermes superagent status` — config loaded, profiles listed, board
   present.

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
