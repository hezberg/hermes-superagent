"""Interactive setup wizard for hermes-superagent.

The non-interactive installer is the engine; this wizard is the
guided front door for a human at a terminal:

    hermes superagent setup          (after bootstrap)
    python3 scripts/install.py --wizard   (from a checkout)

It refuses to start until Hermes itself is ready (the suite builds
on the default profile's setup — it never replaces it), then walks:
worker topology -> per-role provider/model selection -> optional
Feishu entry (paste a dedicated app's credentials, or bind through
Hermes' own setup) -> install -> kanban init -> reminder delivery
-> doctor verdict. Feishu App IDs are checked against every other
profile: one app serves exactly one profile, and a duplicate is a
hard stop with instructions to create a new app.

All decisions are written into superagent.yaml as text edits (the
file's comments survive), and every external action goes through an
injectable runner so the whole flow is testable without a terminal.
"""
import getpass
import os
import re
import shutil
import subprocess
import sys

WORKER_PRESETS = {
    "general": {
        "profile": "sa-worker-general", "role": "general",
        "comment": "everyday tasks: shell, files, web",
        "toolsets": "[terminal, file, web]", "max_concurrent": 2,
    },
    "research": {
        "profile": "sa-worker-research", "role": "research",
        "comment": "reading, synthesis, long-form reporting — no shell",
        "toolsets": "[web, file]", "max_concurrent": 1,
    },
    "deep": {
        "profile": "sa-worker-deep", "role": "deep",
        "comment": "hard reasoning: debugging, design, review",
        "toolsets": "[terminal, file, web]", "max_concurrent": 1,
    },
}
WORKER_ORDER = ["general", "research", "deep"]
TOP_LEVEL_KEYS = ("version", "router", "workers", "entry", "policy",
                  "sources", "watchdog", "events", "limits", "security")


# ---------------------------------------------------------------------------
# IO (injectable for tests)
# ---------------------------------------------------------------------------

class Style:
    """ANSI styling, stdlib only. A wizard nobody can READ is a
    wizard nobody finishes: errors, stops, defaults and successes
    must be visible at a glance. Color turns itself off when the
    output is not a terminal (pipes, captured test output) or when
    NO_COLOR is set; SUPERAGENT_WIZARD_COLOR=always|never overrides."""

    CODES = {"bold": "1", "dim": "2", "red": "31", "green": "32",
             "yellow": "33", "cyan": "36"}

    def __init__(self, enabled=None):
        if enabled is None:
            enabled = self._auto()
        self.enabled = enabled

    @staticmethod
    def _auto():
        forced = os.environ.get("SUPERAGENT_WIZARD_COLOR", "")
        if forced == "always":
            return True
        if forced == "never" or os.environ.get("NO_COLOR"):
            return False
        try:
            return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
        except Exception:
            return False

    def __call__(self, text, *names):
        if not self.enabled or not names:
            return text
        codes = ";".join(self.CODES[n] for n in names)
        return f"\033[{codes}m{text}\033[0m"


class Prompter:
    def __init__(self, input_fn=None, getpass_fn=None, out=None, style=None):
        self._input = input_fn or input
        self._getpass = getpass_fn or getpass.getpass
        self._out = out or print
        self.style = style if style is not None else Style()

    def say(self, msg=""):
        self._out(msg)

    def header(self, step, title):
        s = self.style
        self.say("")
        self.say(s(f"◆ Step {step} — {title}", "bold", "cyan"))
        self.say(s("─" * (len(f"◆ Step {step} — {title}")), "dim"))

    def error(self, msg):
        self.say(self.style(f"✗ {msg}", "bold", "red"))

    def warn(self, msg):
        self.say(self.style(f"! {msg}", "bold", "yellow"))

    def ok(self, msg):
        self.say(self.style(f"✓ {msg}", "bold", "green"))

    def ask(self, prompt, default=""):
        suffix = f" [{default}]" if default else ""
        try:
            answer = self._input(
                f"{self.style(prompt, 'bold')}{self.style(suffix, 'dim')}: ").strip()
        except EOFError:
            return default
        return answer or default

    def secret(self, prompt):
        try:
            return self._getpass(f"{self.style(prompt, 'bold')}: ").strip()
        except EOFError:
            return ""

    def confirm(self, prompt, default=False):
        hint = "Y/n" if default else "y/N"
        answer = self.ask(f"{prompt} ({hint})").lower()
        if not answer:
            return default
        return answer in ("y", "yes")

    def choose(self, title, options, default=0):
        s = self.style
        self.say(s(title, "bold"))
        for i, label in enumerate(options):
            num = s(f"{i + 1}.", "bold", "cyan")
            mark = s("  ← default", "green") if i == default else ""
            text = s(label, "bold") if i == default else label
            self.say(f"  {num} {text}{mark}")
        while True:
            answer = self.ask("Choose", str(default + 1))
            try:
                n = int(answer)
            except ValueError:
                n = -1
            if 1 <= n <= len(options):
                return n - 1
            self.error(f"Please enter a number between 1 and {len(options)}.")


def _default_runner(argv, env=None, interactive=False):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    if interactive:
        proc = subprocess.run(argv, env=full_env)
        return proc.returncode, ""
    proc = subprocess.run(argv, env=full_env, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


# ---------------------------------------------------------------------------
# Pure checks and text surgery (unit-tested without a terminal)
# ---------------------------------------------------------------------------

def _env_value(text, var):
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if line.startswith(var + "="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def default_profile_problem(default_cfg, global_env_text, environ=None):
    """None when Hermes' default profile is ready to build on.

    ("unconfigured", ...) — no model anywhere: the wizard must stop
    and send the operator to Hermes' own setup first.
    ("key-missing", VAR) — the default model names a key variable
    that has no non-empty value: proceeding would rebuild the exact
    401 failure this suite spent a day diagnosing in the field."""
    cfg = default_cfg or {}
    block = cfg.get("model") or {}
    has_block = isinstance(block, dict) and bool(
        block.get("provider") or block.get("default"))
    has_providers = bool(cfg.get("providers")) or bool(cfg.get("custom_providers"))
    if not has_block and not has_providers:
        return ("unconfigured",
                "the default Hermes profile has no model configured yet")
    if has_block:
        var = block.get("api_key_env") or block.get("key_env")
        if var:
            in_file = _env_value(global_env_text, var)
            in_env = (environ or {}).get(var) or ""
            if not in_file and not in_env:
                return ("key-missing", var)
    return None


def find_app_id_conflicts(home, app_id, exclude_profile=None):
    """Where else is this Feishu App ID already in use?

    One Feishu app serves exactly one profile: two profiles polling
    the same app fight over its event stream. Scans the default
    profile and every profile's .env / config.yaml for the id."""
    if not app_id:
        return []
    hits = []

    def scan(label, *paths):
        for path in paths:
            try:
                with open(path, encoding="utf-8") as fh:
                    if app_id in fh.read():
                        hits.append(label)
                        return
            except OSError:
                pass

    scan("the default profile",
         os.path.join(home, ".env"), os.path.join(home, "config.yaml"))
    profiles_dir = os.path.join(home, "profiles")
    try:
        names = sorted(os.listdir(profiles_dir))
    except OSError:
        names = []
    for name in names:
        if name == exclude_profile:
            continue
        scan(f"profile {name}",
             os.path.join(profiles_dir, name, ".env"),
             os.path.join(profiles_dir, name, "config.yaml"))
    return hits


def _worker_block(name):
    p = WORKER_PRESETS[name]
    return (
        f"  - name: {name}\n"
        f"    profile: {p['profile']}\n"
        f"    role: {p['role']} # {p['comment']}\n"
        f"    provider: \"\"\n"
        f"    model: \"\"\n"
        f"    reasoning_effort: \"\"\n"
        f"    toolsets: {p['toolsets']}\n"
        f"    max_concurrent: {p['max_concurrent']}"
    )


def workers_section(names):
    """The workers: section for the chosen topology: chosen workers
    active, the rest present but commented out (opt-in by
    uncommenting, exactly like the shipped template)."""
    lines = [
        "workers:",
        "  # One worker can take every card. Add a worker when a class",
        "  # of work deserves its own model or a tighter toolset —",
        "  # enabling one is uncommenting its block below.",
    ]
    for name in WORKER_ORDER:
        block = _worker_block(name)
        if name in names:
            lines.append(block)
        else:
            lines.append("\n".join("#" + line if line.strip() else "#"
                                   for line in block.split("\n")))
    return "\n".join(lines)


def _replace_section(text, key, new_section):
    """Replace a top-level YAML section (from `key:` to the next
    top-level key) with new text; append when absent."""
    lines = text.split("\n")
    start = None
    end = len(lines)
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if start is None:
            if re.match(rf"^{key}:\s*(#.*)?$", stripped):
                start = i
        elif re.match(r"^[a-z_]+:\s*(#.*)?$", stripped) and \
                stripped.split(":", 1)[0] in TOP_LEVEL_KEYS:
            end = i
            break
    if start is None:
        return text.rstrip("\n") + "\n\n" + new_section + "\n"
    lines[start:end] = new_section.split("\n")
    return "\n".join(lines)


def set_entry_section(text, platform, user_id="", chat_id=""):
    section = (
        "entry:\n"
        f"  platform: \"{platform}\" # empty = no chat entry managed\n"
        f"  user_id: \"{user_id}\" # optional: on a shared bot, route only this sender\n"
        f"  chat_id: \"{chat_id}\" # optional: route only this chat"
    )
    return _replace_section(text, "entry", section)


def remove_env_keys(path, keys):
    """Delete KEY= lines from a .env file, preserving everything
    else. Used to unbind a conflicting platform app from a profile:
    leaving the credentials on disk would let the gateway bring the
    duplicate binding up anyway, wizard or no wizard."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
    except OSError:
        return
    kept = [line for line in lines
            if not any(line.strip().startswith(k + "=") for k in keys)]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(kept).rstrip("\n") + "\n")


def upsert_env_lines(path, pairs):
    """Insert or replace KEY=value lines in a .env file, preserving
    everything else. Used for the router profile's platform
    credentials — operator-owned lines the installer never touches."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
    except OSError:
        lines = []
    seen = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        for key, value in pairs.items():
            if stripped.startswith(key + "="):
                lines[i] = f"{key}={value}"
                seen.add(key)
    for key, value in pairs.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip("\n") + "\n")


# ---------------------------------------------------------------------------
# The wizard
# ---------------------------------------------------------------------------

def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def run_wizard(home, repo, prompter=None, runner=None, environ=None):
    from . import _yaml_load, hermes_provider_menu, load_suite_config
    from .reconcile import set_role_selection

    ui = prompter or Prompter()
    run = runner or _default_runner
    environ = environ if environ is not None else dict(os.environ)
    env = {"HERMES_HOME": home}
    os.environ["HERMES_HOME"] = home  # package helpers resolve home from env
    say = ui.say

    say(ui.style("hermes-superagent — setup wizard", "bold", "cyan"))
    say(ui.style("=" * 34, "dim"))
    ui.header(1, "Hermes readiness")

    # -- 1. Hermes itself ------------------------------------------------
    hermes = shutil.which("hermes")
    if not hermes:
        ui.error("Hermes is not installed (no `hermes` on PATH). This suite")
        say("builds on Hermes and does not install it. Install Hermes")
        say("first (https://hermes-agent.nousresearch.com), then re-run")
        say("this wizard.")
        return 2
    rc, out = run([hermes, "--version"], env=env)
    say(ui.style(f"Hermes: {out.strip().splitlines()[0] if out.strip() else 'found'}", "dim"))

    default_cfg = {}
    raw_default = _read(os.path.join(home, "config.yaml"))
    if raw_default:
        try:
            parsed = _yaml_load(raw_default)
            default_cfg = parsed if isinstance(parsed, dict) else {}
        except Exception:
            default_cfg = {}
    problem = default_profile_problem(
        default_cfg, _read(os.path.join(home, ".env")), environ)
    if problem:
        kind, detail = problem
        if kind == "unconfigured":
            ui.error(f"Cannot continue: {detail}.")
            say("Run Hermes' own setup first — `hermes setup` (or")
            say("`hermes model` to pick a model) — then re-run this wizard.")
        else:
            ui.error(f"Cannot continue: the default model's key variable {detail}")
            say("has no value. Add one line to ~/.hermes/.env:")
            say(f"  {detail}=<your key>")
            say("then re-run this wizard. (An empty or missing key passes")
            say("every naive check and fails only at the first real request.)")
        return 2
    ui.ok("Default Hermes profile: ready.")

    # -- 2. Existing config as defaults ----------------------------------
    suite_dir_path = os.path.join(home, "superagent")
    cfg_path = os.path.join(suite_dir_path, "superagent.yaml")
    existing_text = _read(cfg_path)
    existing_cfg = load_suite_config() if existing_text else {}
    router_profile = (existing_cfg.get("router") or {}).get("profile") or "sa-router"
    existing_workers = [w.get("name") for w in existing_cfg.get("workers") or []
                        if w.get("name") in WORKER_PRESETS]
    if existing_text:
        say("Found an existing superagent config — your current choices")
        say("are the defaults; change what you like, keep the rest.")

    # -- 3. Topology ------------------------------------------------------
    topo_default = 0
    if set(existing_workers) == {"general", "research", "deep"}:
        topo_default = 1
    elif existing_workers and set(existing_workers) != {"general"}:
        topo_default = 2
    ui.header(2, "Workers")
    choice = ui.choose("Which profiles should exist?", [
        "Just the general worker (recommended: one worker takes every card)",
        "All three: general + research + deep",
        "Pick individually",
    ], default=topo_default)
    if choice == 0:
        worker_names = ["general"]
    elif choice == 1:
        worker_names = list(WORKER_ORDER)
    else:
        worker_names = ["general"]
        for extra in ("research", "deep"):
            default_yes = extra in existing_workers
            if ui.confirm(f"Enable the {extra} worker?", default=default_yes):
                worker_names.append(extra)

    # -- 4. Per-role provider/model --------------------------------------
    # The menu offers real selections only: named providers and
    # custom providers (the default profile's own block is what
    # "inherit" means — it is not a selectable name). A selection
    # whose entry already names a model settles BOTH provider and
    # model; the wizard asks for a model only when the entry has
    # none.
    menu = [item for item in hermes_provider_menu(default_cfg)
            if not item.get("default")]
    menu_labels = ["Inherit the default profile's model"] + [
        f"{item['select']} — {item['detail']}" for item in menu
    ]
    ui.header(3, "Models")
    roles = [("Router", router_profile, "router")]
    roles += [(f"Worker {n}", WORKER_PRESETS[n]["profile"], n) for n in worker_names]
    selections = {}
    for label, profile, _kind in roles:
        idx = ui.choose(f"{label} ({profile}) — model:", menu_labels, default=0)
        if idx == 0:
            selections[profile] = ("", "")
            continue
        item = menu[idx - 1]
        provider = item["select"]
        if item.get("model"):
            selections[profile] = (provider, item["model"])
            say(f"  -> {provider} / {item['model']} (as defined in Hermes)")
            continue
        model = ui.ask(f"Model for {profile} (blank = provider default)")
        selections[profile] = (provider, model)

    # Key check for the selections themselves: a chosen provider
    # whose key variable has no value anywhere installs fine and
    # fails only at the first request — surface it NOW (a warning,
    # not a stop: Hermes may resolve the key from a secret store
    # this check cannot see).
    global_env_text = _read(os.path.join(home, ".env"))
    items_by_select = {item["select"]: item for item in menu}
    for _label, profile, _kind in roles:
        provider, _model = selections[profile]
        var = (items_by_select.get(provider) or {}).get("key_var") or ""
        if var and not _env_value(global_env_text, var) \
                and not environ.get(var):
            ui.warn(f"{profile}: provider {provider} reads its key from "
                f"{var}, which has no value in ~/.hermes/.env — add "
                f"{var}=<key> there, or the role cannot call its model.")

    # -- 5. Feishu entry ---------------------------------------------------
    entry_platform = ""
    entry_failed = ""
    delivery = ""
    ui.header(4, "Chat entry")
    feishu_choice = ui.choose("Talk to the Router from chat?", [
        "No chat entry (CLI only)",
        "Feishu — paste a NEW dedicated app's App ID + Secret",
        "Feishu — bind through Hermes' own setup (it offers QR binding)",
    ], default=0)
    if feishu_choice in (1, 2):
        entry_platform = "feishu"
        delivery = "feishu"
        router_env = os.path.join(home, "profiles", router_profile, ".env")
        if feishu_choice == 1:
            while True:
                app_id = ui.ask("Feishu App ID (of the NEW app)")
                if not app_id.startswith("cli_"):
                    say("That does not look like a Feishu App ID (they start")
                    say("with cli_). Try again.")
                    continue
                conflicts = find_app_id_conflicts(
                    home, app_id, exclude_profile=router_profile)
                if conflicts:
                    ui.error(f"STOP: App ID {app_id} is already used by "
                             f"{', '.join(conflicts)}.")
                    say("One Feishu app serves exactly one profile — two")
                    say("profiles on one app fight over its events. Create a")
                    say("NEW app in the Feishu developer console for the")
                    say("Router, then enter its App ID.")
                    if not ui.confirm("Enter a different App ID?", default=True):
                        entry_platform = ""
                        delivery = ""
                        entry_failed = "duplicate App ID, no replacement entered"
                        break
                    continue
                secret = ui.secret("Feishu App Secret (hidden, stored only in the router profile's .env)")
                if not secret:
                    say("No secret entered — skipping the Feishu entry.")
                    entry_platform = ""
                    delivery = ""
                    entry_failed = "no App Secret entered"
                    break
                upsert_env_lines(router_env, {
                    "FEISHU_APP_ID": app_id, "FEISHU_APP_SECRET": secret})
                ui.ok("Credentials stored in the router profile's .env.")
                break
        else:
            # Bind through Hermes' own setup, then apply the SAME
            # hard rule as the paste path: a duplicate app is a
            # stop, not a warning. The conflicting credentials must
            # not stay on disk either — the gateway would bring the
            # duplicate binding up regardless of what the wizard
            # decided.
            while True:
                say("Launching Hermes' own setup for the router profile —")
                say("follow its prompts (QR binding is offered there).")
                run([hermes, "--profile", router_profile, "gateway", "setup"],
                    env=env, interactive=True)
                bound_id = _env_value(_read(router_env), "FEISHU_APP_ID")
                if not bound_id:
                    say("No FEISHU_APP_ID landed in the router profile — the")
                    say("entry is NOT wired. Re-run the wizard when ready.")
                    entry_platform = ""
                    delivery = ""
                    entry_failed = "Hermes setup bound no app"
                    break
                conflicts = find_app_id_conflicts(
                    home, bound_id, exclude_profile=router_profile)
                if not conflicts:
                    ui.ok(f"Bound app {bound_id} to {router_profile}.")
                    break
                ui.error(f"STOP: the app you just bound ({bound_id}) is already")
                say(f"used by {', '.join(conflicts)}. One Feishu app serves")
                say("exactly one profile — two profiles on one app fight")
                say("over its event stream, so this binding cannot stand.")
                if ui.confirm(
                        "Remove it from the router profile and bind a NEW app?",
                        default=True):
                    remove_env_keys(router_env,
                                    ["FEISHU_APP_ID", "FEISHU_APP_SECRET"])
                    say("Removed. Create a NEW app in the Feishu developer")
                    say("console first if you have not, then bind that one.")
                    continue
                if ui.confirm(
                        "Remove it and continue WITHOUT a Feishu entry?",
                        default=True):
                    remove_env_keys(router_env,
                                    ["FEISHU_APP_ID", "FEISHU_APP_SECRET"])
                    say("Removed from the router profile.")
                else:
                    say("Left in place at your choice — the duplicate WILL")
                    say("conflict at the gateway until one profile gets its")
                    say("own app. The wizard will not record this entry.")
                entry_platform = ""
                delivery = ""
                entry_failed = f"bound app {bound_id} duplicates another profile"
                break

    # -- 6. Write the config ----------------------------------------------
    ui.header(5, "Install")
    base_text = existing_text or _read(os.path.join(repo, "config", "superagent.yaml"))
    text = _replace_section(base_text, "workers", workers_section(worker_names))
    text = set_entry_section(text, entry_platform)
    os.makedirs(suite_dir_path, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    for _label, profile, _kind in roles:
        provider, model = selections[profile]
        set_role_selection(suite_dir_path, profile, provider, model)
    say("Config written to ~/.hermes/superagent/superagent.yaml")

    # -- 7. Install ---------------------------------------------------------
    installer = os.path.join(repo, "scripts", "install.py")
    rc, out = run([sys.executable, installer], env=env)
    say(out.rstrip())
    if rc != 0:
        ui.error("The installer did not complete — fix the item above and")
        say("re-run this wizard (your choices are saved in the config).")
        return rc

    # -- 8. Kanban + delivery ----------------------------------------------
    rc, _out = run([hermes, "kanban", "init"], env=env)
    if rc == 0:
        ui.ok("Kanban board: ready.")
    else:
        ui.warn("Kanban board: init returned an error — check `hermes kanban init`.")
    if delivery:
        rc, out = run([hermes, "cron", "list"], env=env)
        job_id = None
        for line in out.splitlines():
            if "superagent-reminder-tick" in line:
                parts = line.split()
                if parts:
                    job_id = parts[0]
                    break
        if job_id:
            run([hermes, "cron", "edit", job_id, "--deliver", delivery], env=env)
            say(f"Reminder delivery: {delivery} (job {job_id}).")
        else:
            say("Reminder delivery: set it once with "
                f"`hermes cron edit <tick job id> --deliver {delivery}`.")

    # -- 9. Doctor verdict ---------------------------------------------------
    try:
        from . import _doctor_findings

        findings = _doctor_findings()
        errors = [f for f in findings if f.get("level") == "error"]
        warns = [f for f in findings if f.get("level") == "warn"]
        ui.header(6, "Verify")
        for f in errors:
            ui.error(f["text"])
            if f.get("fix"):
                say(f"        fix: {f['fix']}")
        for f in warns:
            ui.warn(f["text"])
            if f.get("fix"):
                say(f"        fix: {f['fix']}")
        if errors:
            ui.error("Installed, but doctor reports errors — resolve them above.")
            return 1
        ui.ok("Doctor: all checks pass.")
    except Exception:
        say("Doctor check could not run here; run `hermes superagent doctor`.")

    # -- 10. Go live ---------------------------------------------------------
    if entry_platform and ui.confirm(
            "Restart the gateway now so the chat entry goes live?", default=True):
        run([hermes, "gateway", "restart"], env=env)
        say("Gateway restarted.")
    say("")
    if entry_failed:
        ui.error(f"Feishu entry: NOT configured — {entry_failed}.")
        say("Everything else is installed and usable from the CLI; re-run")
        say("`hermes superagent setup` with a dedicated app to finish it.")
        return 1
    ui.ok("You are set. Talk to the Router:")
    say(f"  hermes --profile {router_profile}")
    if entry_platform:
        say(f"  or DM your new {entry_platform} bot — its answers come from the Router,")
        say("  and finished tasks report back into that chat.")
    say('First task idea: "Sort out X and report back when it is done."')
    return 0
