"""hermes-superagent plugin.

In-process pieces of the Super-agent layer:
  - /tasks command      — Kanban board summary for the human
  - /stop command       — ask the Router to block a task (via kanban tools)
  - sa_status tool      — machine-readable status for the Router / Watchdog
  - activity hooks      — append-only JSONL log under
                          $HERMES_HOME/superagent/activity.jsonl; this is
                          the raw material the Watchdog reasons over
  - `hermes superagent` — CLI: status | watchdog (report-only)

Design rules:
  - Every hook is passive and exception-proof: this plugin must never be
    able to break the host gateway.
  - The plugin reads the Kanban board directly (read-only sqlite) instead
    of shelling out to the CLI.
"""
import json
import logging
import os
import sqlite3
import time
from datetime import datetime

logger = logging.getLogger(__name__)

PLUGIN_VERSION = "0.8.1"


# --------------------------------------------------------------------------
# Paths & config
# --------------------------------------------------------------------------

def hermes_home():
    return os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")


def suite_dir():
    return os.path.join(hermes_home(), "superagent")


def board_path():
    return os.path.join(hermes_home(), "kanban.db")


def _yaml_load(text):
    """Parse YAML text. PyYAML when importable; otherwise the bundled
    subset parser (miniyaml) — Hermes' bundled CLI python ships no
    PyYAML, and silently reading every config as empty is how doctor
    spent days reporting a valid config as 'not loaded'."""
    try:
        import yaml

        return yaml.safe_load(text) or {}
    except ImportError:
        from .miniyaml import parse

        return parse(text) or {}


def load_suite_config():
    """Read the installed superagent.yaml copy, or {} if not installed."""
    path = os.path.join(suite_dir(), "superagent.yaml")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return _yaml_load(fh.read())
    except Exception:
        return {}


def load_default_config():
    """The default Hermes profile's config.yaml, or {}."""
    try:
        with open(os.path.join(hermes_home(), "config.yaml"), encoding="utf-8") as fh:
            cfg = _yaml_load(fh.read())
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _entry_detail(entry):
    bits = []
    if (entry or {}).get("base_url"):
        bits.append(str(entry["base_url"]))
    model = (entry or {}).get("default") or (entry or {}).get("model")
    if model:
        bits.append(f"model {model}")
    var = (entry or {}).get("api_key_env") or (entry or {}).get("key_env")
    if var:
        bits.append(f"key var {var}")
    return ", ".join(bits)


def hermes_provider_menu(default_cfg):
    """What a role can select: the default profile's model plus every
    named provider in its config. Names and non-secret facts only."""
    items = []
    block = (default_cfg or {}).get("model") or {}
    if isinstance(block, dict) and (block.get("provider") or block.get("default")):
        items.append({
            "select": block.get("provider") or "custom",
            "detail": "default profile model: "
                      + str(block.get("default") or block.get("model") or "?")
                      + (f", key var {block.get('api_key_env') or block.get('key_env')}"
                         if (block.get("api_key_env") or block.get("key_env")) else ""),
            "default": True,
        })
    providers = (default_cfg or {}).get("providers")
    if isinstance(providers, dict):
        for key, entry in providers.items():
            if isinstance(entry, dict):
                items.append({"select": entry.get("name") or key,
                              "detail": _entry_detail(entry), "default": False})
    custom = (default_cfg or {}).get("custom_providers")
    if isinstance(custom, list):
        for entry in custom:
            if isinstance(entry, dict) and entry.get("name"):
                items.append({"select": entry["name"],
                              "detail": _entry_detail(entry), "default": False})
    return items


def resolved_role_key_vars(cfg, default_cfg):
    """{profile: key variable name} for every role, resolved the way
    the installer resolves selections: a legacy suite provider, a
    named Hermes provider entry, or the default model block."""
    block = (default_cfg or {}).get("model") or {}
    block_var = block.get("api_key_env") or block.get("key_env") or ""
    block_provider = str(block.get("provider") or "").lower()
    entries = {}
    providers = (default_cfg or {}).get("providers")
    if isinstance(providers, dict):
        for key, entry in providers.items():
            if isinstance(entry, dict):
                var = entry.get("api_key_env") or entry.get("key_env") or ""
                for nm in (key, entry.get("name"), entry.get("provider_key")):
                    if nm:
                        entries[str(nm).lower().removeprefix("custom:")] = var
    custom = (default_cfg or {}).get("custom_providers")
    if isinstance(custom, list):
        for entry in custom:
            if isinstance(entry, dict) and entry.get("name"):
                entries[str(entry["name"]).lower()] = \
                    entry.get("api_key_env") or entry.get("key_env") or ""
    legacy = cfg.get("providers") or {}
    out = {}
    roles = [cfg.get("router") or {}] + list(cfg.get("workers") or [])
    for role in roles:
        if not isinstance(role, dict) or not role.get("profile"):
            continue
        prov = str(role.get("provider") or "").strip()
        var = ""
        if prov in legacy:
            var = (legacy[prov] or {}).get("api_key_env") or ""
        elif prov:
            norm = prov.lower().removeprefix("custom:")
            if norm in entries:
                var = entries[norm]
            elif prov.lower() == block_provider:
                var = block_var
        else:
            var = block_var
        if var:
            out[role["profile"]] = var
    return out


# --------------------------------------------------------------------------
# Kanban board (read-only)
# --------------------------------------------------------------------------

def _board_connect():
    path = board_path()
    if not os.path.exists(path):
        return None
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def board_counts():
    """Return {status: count} from the kanban board, or None if absent."""
    conn = _board_connect()
    if conn is None:
        return None
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) FROM tasks GROUP BY status"
        ).fetchall()
        return {status: count for status, count in rows}
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _epoch(value):
    """Best-effort conversion of a board timestamp to epoch seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def board_tasks():
    """Return task rows as plain dicts for the watchdog logic."""
    conn = _board_connect()
    if conn is None:
        return []
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM tasks").fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    tasks = []
    for row in rows:
        d = dict(row)
        tasks.append(
            {
                "id": d.get("id"),
                "title": d.get("title"),
                "status": d.get("status"),
                "assignee": d.get("assignee") or d.get("profile"),
                "updated_at": _epoch(d.get("updated_at")),
                "last_heartbeat": _epoch(d.get("last_heartbeat") or d.get("heartbeat_at")),
            }
        )
    return tasks


def board_reports():
    """Latest SA-REPORT kind per task, parsed from board comments.

    The board's comment storage is a Hermes implementation detail; this
    reader is deliberately defensive: it looks for any comment-like
    table with task/body-ish columns and gives up quietly otherwise.
    Returns {task_id: report-kind}.
    """
    from .reports import parse_report

    conn = _board_connect()
    if conn is None:
        return {}
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        table = next((t for t in tables if "comment" in t.lower()), None)
        if table is None:
            return {}
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        task_col = next((c for c in cols if "task" in c.lower()), None)
        body_col = next(
            (c for c in cols if c.lower() in ("body", "text", "content", "comment")),
            None,
        )
        if task_col is None or body_col is None:
            return {}
        order = "rowid"  # latest write wins
        rows = conn.execute(
            f"SELECT {task_col}, {body_col} FROM {table} ORDER BY {order}"
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    latest = {}
    for task_id, body in rows:
        kind = parse_report(body if isinstance(body, str) else "")
        if kind is not None:
            latest[task_id] = kind  # later rows overwrite: latest wins
    return latest


def board_events():
    """Native board events per task: {task_id: [{type, ts, ...}, ...]}.

    Reads the board's event table (Hermes writes one row per lifecycle
    transition: created / claimed / completed / blocked / …). Same
    defensive posture as board_reports(): the storage layout is a
    Hermes implementation detail, so any mismatch quietly yields {}.
    Events are returned in write order (oldest first). When an event
    carries a JSON payload, its `summary` and `artifacts` fields are
    lifted onto the event dict (that is where kanban_complete records
    the handoff).
    """
    conn = _board_connect()
    if conn is None:
        return {}
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        table = next((t for t in tables if "event" in t.lower()), None)
        if table is None:
            return {}
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        task_col = next((c for c in cols if "task" in c.lower()), None)
        type_col = next(
            (c for c in cols if c.lower() in ("type", "event", "kind", "name")),
            None,
        )
        ts_col = next(
            (c for c in cols if "creat" in c.lower() or c.lower() in ("ts", "time", "at")),
            None,
        )
        payload_col = next(
            (c for c in cols if c.lower() in ("payload", "data", "detail", "details")),
            None,
        )
        if task_col is None or type_col is None:
            return {}
        ts_expr = ts_col if ts_col else "NULL"
        payload_expr = payload_col if payload_col else "NULL"
        rows = conn.execute(
            f"SELECT {task_col}, {type_col}, {ts_expr}, {payload_expr} FROM {table} ORDER BY rowid"
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    events = {}
    for task_id, etype, ts, payload in rows:
        event = {"type": etype, "ts": _epoch(ts)}
        if isinstance(payload, str) and payload:
            try:
                data = json.loads(payload)
            except ValueError:
                data = None
            if isinstance(data, dict):
                if data.get("summary"):
                    event["summary"] = data["summary"]
                if data.get("artifacts"):
                    event["artifacts"] = data["artifacts"]
        events.setdefault(task_id, []).append(event)
    return events


# --------------------------------------------------------------------------
# Journal (suite-level memory of finished work)
# --------------------------------------------------------------------------

def _journal_jsonl():
    return os.path.join(suite_dir(), "journal.jsonl")


def journal_entries():
    """All journal entries, oldest first. [] when none exist yet."""
    entries = []
    try:
        with open(_journal_jsonl(), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        pass
    return entries


def sync_journal():
    """Record any newly-terminal cards into the journal.

    Returns the list of entries added by this sync. Safe to call
    repeatedly (idempotent by entry key). Failures are swallowed into
    an empty result: the journal is memory, not a gate.
    """
    from .journal import entry_key, new_entries, render_journal_md

    try:
        existing = journal_entries()
        seen = {entry_key(e) for e in existing}
        fresh = new_entries(board_tasks(), board_events(), seen)
        if not fresh:
            return []
        os.makedirs(suite_dir(), exist_ok=True)
        with open(_journal_jsonl(), "a", encoding="utf-8") as fh:
            for entry in fresh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        with open(os.path.join(suite_dir(), "journal.md"), "w", encoding="utf-8") as fh:
            fh.write(render_journal_md(existing + fresh))
        return fresh
    except Exception:
        logger.debug("journal sync failed", exc_info=True)
        return []


# --------------------------------------------------------------------------
# Doctor (whole-install health check, in prose)
# --------------------------------------------------------------------------

def run_reminder_pass(tasks, events_by_task, stalled_ids, watchdog_cfg):
    """One reminder pass: find situations needing the person, keep
    only the ones the ledger says are due, record them, and store the
    prose lines in the outbox (store-first delivery). Returns the due
    list. Shared by the watchdog command and the tick script."""
    from .reminders import (
        ReminderLedger,
        candidates,
        filter_due,
        render_reminder_lines,
        settings_from,
    )

    now = time.time()
    settings = settings_from(watchdog_cfg)
    cands = candidates(tasks, events_by_task, stalled_ids, settings, now)
    ledger = ReminderLedger(os.path.join(suite_dir(), "reminders.json"))
    state = ledger.load()
    due = filter_due(cands, state, settings, now)
    ledger.prune([c["fingerprint"] for c in cands])
    if due:
        lines = render_reminder_lines(due)
        try:
            from .outbox import Outbox

            box = Outbox(os.path.join(suite_dir(), "outbox.json"))
            for cand, line in zip(due, lines):
                box.enqueue(cand["task_id"], "router", line, now=now)
        except Exception:
            pass
        ledger.record(due, now)
    return due


def _doctor_findings():
    from . import doctor as doc

    cfg = load_suite_config()
    router = cfg.get("router") or {}
    workers = cfg.get("workers") or []
    findings = []
    findings += doc.check_config_loaded(cfg, router.get("profile"), len(workers))

    names = [router.get("profile")] + [w.get("profile") for w in workers]
    profile_cfgs, profile_texts, allow_private = {}, {}, {}
    for name in names:
        if not name:
            continue
        path = os.path.join(hermes_home(), "profiles", name, "config.yaml")
        text = None
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            pass
        profile_texts[name] = text
        parsed = {}
        if text:
            try:
                parsed = _yaml_load(text)
            except Exception:
                parsed = {}
        profile_cfgs[name] = parsed
        allow_private[name] = bool(
            ((parsed.get("security") or {}).get("allow_private_urls"))
        )
    if router.get("profile"):
        findings += doc.check_router_toolsets(
            router["profile"], profile_cfgs.get(router["profile"])
        )
    for w in workers:
        if w.get("profile"):
            findings += doc.check_worker_profile(
                w["profile"], profile_cfgs.get(w["profile"])
            )
    findings += doc.check_smart_quotes(profile_texts)

    env_files = [os.path.join(hermes_home(), ".env")] + [
        os.path.join(hermes_home(), "profiles", n, ".env") for n in names if n
    ]
    env_texts = []
    for path in env_files:
        try:
            with open(path, encoding="utf-8") as fh:
                env_texts.append(fh.read())
        except OSError:
            pass
    # Presence means a non-empty VALUE (see doctor.presence_from_env_texts):
    # a bare `KEY=` line is a missing key, not a present one.
    presence = doc.presence_from_env_texts(env_texts, os.environ)
    # Key variables follow each role's selection (a named Hermes
    # provider, the default model block, or a legacy suite provider)
    # — the suite declares none of its own.
    default_cfg = load_default_config()
    role_vars = resolved_role_key_vars(cfg, default_cfg)
    providers_view = {}
    roles_all = [cfg.get("router") or {}] + list(cfg.get("workers") or [])
    for role in roles_all:
        if not isinstance(role, dict) or not role.get("profile"):
            continue
        var = role_vars.get(role["profile"])
        if var:
            label = str(role.get("provider") or "").strip() or "default profile"
            providers_view[label] = {"api_key_env": var}
    env_present = {v: presence.get(v, False) for v in role_vars.values()}
    findings += doc.check_key_env(providers_view, env_present)
    # Convergence: a profile copy that differs from the global .env
    # is a stale key still being sent. Compare values here; doctor
    # receives only names of the offenders.
    from .reconcile import _read_env

    global_env = _read_env(os.path.join(hermes_home(), ".env"))
    stale = {}
    for profile, var in role_vars.items():
        if var not in global_env:
            continue
        profile_env = _read_env(os.path.join(hermes_home(), "profiles", profile, ".env"))
        if var in profile_env and profile_env[var] != global_env[var]:
            stale.setdefault(profile, []).append(var)
    findings += doc.check_key_convergence(stale)
    rendered_providers = {
        n: {"base_url": ((c.get("model") or {}).get("base_url") or "")}
        for n, c in profile_cfgs.items() if c
    }
    findings += doc.check_private_base_url(rendered_providers)

    security = cfg.get("security") or {}
    expected_private = security.get("allow_private_urls")
    if expected_private is not None:
        expected_private = bool(expected_private)
    findings += doc.check_private_urls(expected_private, allow_private)

    plugin_present = os.path.isdir(
        os.path.join(hermes_home(), "plugins", "superagent")
    )
    enabled_list, disabled_list = None, []
    try:
        with open(
            os.path.join(hermes_home(), "config.yaml"), encoding="utf-8"
        ) as fh:
            default_cfg = _yaml_load(fh.read())
        plugins_cfg = default_cfg.get("plugins") or {}
        if isinstance(plugins_cfg.get("enabled"), list):
            enabled_list = plugins_cfg["enabled"]
        if isinstance(plugins_cfg.get("disabled"), list):
            disabled_list = plugins_cfg["disabled"]
    except Exception:
        pass
    findings += doc.check_plugin_enablement(
        enabled_list, disabled_list, plugin_present
    )

    manifest_version, installed_epoch = None, None
    try:
        with open(
            os.path.join(suite_dir(), "manifest.json"), encoding="utf-8"
        ) as fh:
            manifest = json.load(fh)
        manifest_version = manifest.get("version")
        installed_epoch = datetime.strptime(
            manifest.get("installed_at") or "", "%Y-%m-%dT%H:%M:%S%z"
        ).timestamp()
    except Exception:
        pass
    try:
        config_mtime = os.path.getmtime(
            os.path.join(suite_dir(), "superagent.yaml")
        )
    except OSError:
        config_mtime = None
    findings += doc.check_install_drift(
        manifest_version, PLUGIN_VERSION, config_mtime, installed_epoch
    )
    findings += doc.check_board(board_counts())
    return findings


# --------------------------------------------------------------------------
# Activity log (hooks)
# --------------------------------------------------------------------------

def _log_activity(event):
    try:
        os.makedirs(suite_dir(), exist_ok=True)
        event = dict(event)
        event.setdefault("ts", time.time())
        with open(os.path.join(suite_dir(), "activity.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass  # observability must never break the host


def _on_session_start(**kwargs):
    _log_activity({"hook": "on_session_start"})


def _on_session_end(**kwargs):
    _log_activity({"hook": "on_session_end"})


def _on_post_tool_call(tool_name=None, **kwargs):
    _log_activity({"hook": "post_tool_call", "tool": tool_name})


# --------------------------------------------------------------------------
# Status (shared by tool, command and CLI)
# --------------------------------------------------------------------------

def status_payload():
    cfg = load_suite_config()
    counts = board_counts()
    from .gate import accept_mode

    recent = [
        {
            "title": e.get("title"),
            "assignee": e.get("assignee"),
            "outcome": e.get("outcome"),
            "ts": e.get("ts"),
        }
        for e in journal_entries()[-5:]
    ]
    payload = {
        "plugin_version": PLUGIN_VERSION,
        "config_loaded": bool(cfg),
        "router_profile": (cfg.get("router") or {}).get("profile"),
        "workers": [w.get("profile") for w in cfg.get("workers") or []],
        "watchdog_authority": (cfg.get("watchdog") or {}).get("authority", "report-only"),
        "accept_mode": accept_mode(cfg.get("policy"), cfg.get("events")),
        "board": counts,
        "recent_outcomes": recent,
    }
    return payload


def status_text():
    p = status_payload()
    if p["board"] is None:
        board = "kanban board: not initialized (no kanban.db yet)"
    else:
        board = "kanban board: " + ", ".join(
            f"{k}={v}" for k, v in sorted(p["board"].items())
        )
    text = (
        f"superagent v{p['plugin_version']} | config: "
        f"{'loaded' if p['config_loaded'] else 'NOT loaded'} | "
        f"router: {p['router_profile']} | accept: {p['accept_mode']} | "
        f"watchdog: {p['watchdog_authority']}\n{board}"
    )
    if p["recent_outcomes"]:
        from .journal import render_digest

        text += "\n" + render_digest(journal_entries(), limit=3)
    return text


def handle_sa_status(params, **kwargs):
    return json.dumps(status_payload(), ensure_ascii=False)


# --------------------------------------------------------------------------
# Gateway commands
# --------------------------------------------------------------------------

async def cmd_tasks(ctx, args="", **kwargs):
    return status_text()


async def cmd_stop(ctx, args="", **kwargs):
    task_id = (args or "").strip()
    if not task_id:
        return "Usage: /stop <task-id> — ask the Router to block that task."
    # The Router owns the board; go through its kanban tools when available.
    try:
        result = ctx.dispatch_tool("kanban_block", {"task_id": task_id})
        return f"Block requested for {task_id}: {result}"
    except Exception as exc:
        return (
            f"Could not block {task_id} from here ({exc}). "
            "The task is untouched; ask the Router to block it instead."
        )


# --------------------------------------------------------------------------
# CLI: hermes superagent status|watchdog
# --------------------------------------------------------------------------

def _cli_setup(parser):
    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser("status", help="Show superagent status")
    sub.add_parser("watchdog", help="Report stalled tasks (report-only)")
    sub.add_parser("digest", help="Sync the journal and print recent outcomes")
    sub.add_parser("doctor", help="Health-check the whole install, in plain language")
    recall = sub.add_parser("recall", help="Search past outcomes in the journal")
    recall.add_argument("query", nargs="*", help="Keyword(s) to search for")
    sub.add_parser("reminders", help="Show the reminder ledger for unclosed work")
    sub.add_parser("providers", help="List the providers/models in your Hermes config that roles can select")
    sub.add_parser("upgrade", help="Upgrade the suite in place (pulls its source, re-runs the installer)")
    set_model = sub.add_parser(
        "set-model", help="Set one profile's model in superagent.yaml and apply it now")
    set_model.add_argument("profile", help="Profile name, e.g. sa-worker-deep")
    set_model.add_argument("model", help="Model name, or 'inherit' to use the default profile's model")


def _cli_handler(args):
    sub = getattr(args, "subcommand", None) or "status"
    if sub not in ("upgrade", "set-model"):
        # A hand-edited config applies itself on the next command;
        # nobody should have to remember a separate apply step.
        try:
            from .reconcile import maybe_reconcile

            try:
                role_vars = resolved_role_key_vars(
                    load_suite_config(), load_default_config())
            except Exception:
                role_vars = {}
            result = maybe_reconcile(hermes_home(), suite_dir(), interactive=True,
                                     role_vars=role_vars)
            if result["status"] == "reconciled":
                print("(Applied your superagent.yaml changes first.)")
            elif result["status"] == "failed" and result.get("message"):
                print(result["message"])
        except Exception:
            pass
    if sub == "set-model":
        from .reconcile import maybe_reconcile, set_role_model

        model = "" if args.model == "inherit" else args.model
        if not set_role_model(suite_dir(), args.profile, model):
            known = []
            cfg = load_suite_config()
            if (cfg.get("router") or {}).get("profile"):
                known.append(cfg["router"]["profile"])
            known += [w.get("profile") for w in cfg.get("workers") or [] if w.get("profile")]
            print(f"No role with profile '{args.profile}'. Known: {', '.join(known) or '(none)'}")
            return 1
        result = maybe_reconcile(hermes_home(), suite_dir(), interactive=True)
        if result["status"] == "failed":
            print(result.get("message") or "The change was saved but could not be applied.")
            return 1
        print(f"{args.profile}: model set to {model or '(inherit the default profile)'} and applied.")
        return 0
    if sub == "providers":
        menu = hermes_provider_menu(load_default_config())
        if not menu:
            print("No providers or models found in your default Hermes config "
                  "(~/.hermes/config.yaml). Add one in Hermes first "
                  "(Settings -> Providers, or hermes setup).")
            return 0
        print("Providers in your Hermes config — select by name in superagent.yaml "
              "(provider: <name>), or leave provider/model empty for the default:")
        for item in menu:
            tag = " (default)" if item.get("default") else ""
            detail = f" — {item['detail']}" if item.get("detail") else ""
            print(f"  {item['select']}{tag}{detail}")
        return 0
    if sub == "doctor":
        from .doctor import summarize

        findings = _doctor_findings()
        marks = {"ok": "✓", "warn": "⚠", "error": "✗"}
        print("superagent doctor:")
        for f in findings:
            print(f"{marks.get(f['level'], '?')} {f['text']}")
            if f.get("fix"):
                print(f"  Fix: {f['fix']}")
        print(summarize(findings))
        return 1 if any(f["level"] == "error" for f in findings) else 0
    if sub == "recall":
        from .journal import render_digest, search_entries

        sync_journal()
        query = " ".join(getattr(args, "query", None) or []).strip()
        if not query:
            print("Usage: hermes superagent recall <keyword> - search past outcomes in the journal.")
            return 2
        matches = search_entries(journal_entries(), query)
        if not matches:
            print(f"No past outcomes match '{query}'.")
            return 0
        print(f"Past outcomes matching '{query}' ({len(matches)}):")
        print(render_digest(matches, limit=10))
        return 0
    if sub == "digest":
        from .journal import render_digest

        fresh = sync_journal()
        if fresh:
            print(f"journal: recorded {len(fresh)} new outcome(s)")
        print(render_digest(journal_entries()))
        return 0
    if sub == "watchdog":
        fresh = sync_journal()
        if fresh:
            print(f"journal: recorded {len(fresh)} new outcome(s)")
        from .reports import derive_report, stage_for
        from .watchdog_logic import find_stalled

        cfg = load_suite_config()
        wd = cfg.get("watchdog") or {}
        tasks = board_tasks()
        reports = board_reports()
        events = board_events()
        for t in tasks:
            if t.get("status") in ("done", "archived"):
                continue
            kind = derive_report(
                t.get("status"),
                events.get(t.get("id")),
                reports.get(t.get("id")),
            )
            stage = stage_for(
                latest_report=kind,
                has_assignment=bool(t.get("assignee"))
                or t.get("status") in ("running", "in_progress"),
            )
            print(f"watchdog: task={t.get('id')} status={t.get('status')} stage={stage}")
        findings = find_stalled(
            tasks,
            time.time(),
            stall_minutes=wd.get("stall_minutes", 30),
            heartbeat_stale_minutes=wd.get("heartbeat_stale_minutes", 15),
        )
        if not findings:
            print("watchdog: no stalled tasks")
        for f in findings:
            print(
                f"watchdog: STALLED task={f['task_id']} assignee={f['assignee']} "
                f"reasons={','.join(f['reasons'])} (authority="
                f"{wd.get('authority', 'report-only')}; no action taken in report-only mode)"
            )
        due = run_reminder_pass(tasks, events, {f["task_id"] for f in findings}, wd)
        for cand in due:
            print(
                f"reminder: due kind={cand['kind']} task={cand['task_id']} "
                f"count={cand['count']} (recorded in the ledger and outbox; delivery is the cron/Router's job)"
            )
        return 0
    if sub == "upgrade":
        from .upgrade import run_upgrade

        print("Upgrading hermes-superagent (fetching source + converging)...")
        return run_upgrade(hermes_home(), suite_dir())
    if sub == "reminders":
        from .reminders import ReminderLedger

        state = ReminderLedger(
            os.path.join(suite_dir(), "reminders.json")
        ).load()
        rows = state.get("rows", [])
        if not rows:
            print("The reminder ledger is empty: no unclosed work has been reminded about yet.")
            return 0
        print(f"Reminder ledger ({len(rows)} open situation(s)):")
        for row in rows:
            when = datetime.fromtimestamp(row.get("last_at") or 0).strftime(
                "%Y-%m-%d %H:%M"
            )
            print(
                f"- {row['task_id']} | {row['kind']} | reminded {row['count']}x | last {when}"
            )
        return 0
    print(status_text())
    return 0


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------

SA_STATUS_SCHEMA = {
    "name": "sa_status",
    "description": (
        "Report hermes-superagent status: config loaded or not, router "
        "profile, worker profiles, watchdog authority, and Kanban board "
        "task counts by status."
    ),
    "parameters": {"type": "object", "properties": {}},
}


def register(ctx):
    ctx.register_tool(
        name="sa_status",
        toolset="superagent",
        schema=SA_STATUS_SCHEMA,
        handler=handle_sa_status,
    )
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_command(
        "tasks", cmd_tasks, "Show the superagent Kanban board summary"
    )
    ctx.register_command("stop", cmd_stop, "Block a kanban task by id")
    ctx.register_cli_command(
        "superagent",
        "Super-agent layer status and watchdog",
        _cli_setup,
        _cli_handler,
    )
    for name, dirname in (("router-superagent", "router"), ("worker-superagent", "worker")):
        skill_path = os.path.join(os.path.dirname(__file__), "skills", dirname)
        if os.path.isdir(skill_path):
            try:
                ctx.register_skill(name, skill_path)
            except Exception:
                logger.debug("register_skill unavailable; installer copies the skill instead")
    logger.info("hermes-superagent plugin v%s registered", PLUGIN_VERSION)
