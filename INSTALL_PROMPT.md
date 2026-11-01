# Install prompt

Paste the block below into a Hermes chat (the default profile, CLI or
Desktop) on the machine where you want hermes-superagent installed.
Hermes does the whole setup itself, following SETUP.md; the only step
that stays with you is entering your API key — in your own terminal,
never in the chat.

---

Please install and configure hermes-superagent for me, following the SETUP.md in its repo throughout:

1. Start with the guided install (the source must land inside Hermes' own directory — do not clone anything into my home directory): `curl -fsSL https://raw.githubusercontent.com/hezberg/hermes-superagent/main/bootstrap.sh | sh`. It generates the config file and stops; the repo lives at `~/.hermes/superagent/src` — read SETUP.md there.
2. Read SETUP.md in full and follow it: probe the environment first, then ask me the questions one at a time (one question per message, each with your recommended answer), then summarize the plan in a single message for my confirmation — only start once I confirm.
3. Hard rules:
   - Never ask me to send an API key in chat, and never read, print or store any key value. When a key is needed, give me the exact line (`<VAR_NAME>=<key>`, to go into `~/.hermes/.env`); I will do it in my own terminal — you only verify the variable name is in place.
   - Configuration: you ask me the questions in this chat and write the config yourself, following SETUP.md. The interactive wizard (`hermes superagent setup`) is a terminal tool for me to run myself — do not try to drive it from this chat. Writing the config by hand: run `python3 scripts/install.py` once — it generates ~/.hermes/superagent/superagent.yaml and stops; write the answers I gave into that file (show me before writing), then run it once more to finish the install. Never hand-edit any rendered file under `~/.hermes/profiles/`, and never leave any of my config in the repo tree.
   - If you are running inside a gateway conversation, warn me before restarting the gateway that the conversation will drop, and make the restart the very last step.
   - If this conversation is itself running over Feishu, the Feishu app carrying it belongs to the default profile: never move, rebind or copy that app to the Router — two profiles bound to one app fight over its event stream. The Router needs a separate app of its own; if I don't have one, skip the chat entry and say so in the handover.
4. Done means every item checks out: the install succeeded; `hermes superagent status` works; `hermes superagent doctor` shows no ✗ at all; finally, run a small test task through sa-router and confirm a card lands on the board and completes.
5. Reminder delivery: after the install, ask me which platform the unfinished-work reminders should be delivered to, and point the cron job's `--deliver` there; if I say I'll decide later, skip it and write the fix-up steps into the handover.
6. When everything is done, hand over in plain language: how I dispatch work, where I watch progress, and how I uninstall.
