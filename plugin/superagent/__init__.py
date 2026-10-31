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

PLUGIN_VERSION = "0.2.0"


# --------------------------------------------------------------------------
# Paths & config
# --------------------------------------------------------------------------

def hermes_home():
    return os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")


def suite_dir():
    return os.path.join(hermes_home(), "superagent")


def board_path():
    return os.path.join(hermes_home(), "kanban.db")


def load_suite_config():
    """Read the installed superagent.yaml copy, or {} if not installed."""
    path = os.path.join(suite_dir(), "superagent.yaml")
    try:
        import yaml

        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


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

    payload = {
        "plugin_version": PLUGIN_VERSION,
        "config_loaded": bool(cfg),
        "router_profile": (cfg.get("router") or {}).get("profile"),
        "workers": [w.get("profile") for w in cfg.get("workers") or []],
        "watchdog_authority": (cfg.get("watchdog") or {}).get("authority", "report-only"),
        "accept_mode": accept_mode(cfg.get("policy"), cfg.get("events")),
        "board": counts,
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
    return (
        f"superagent v{p['plugin_version']} | config: "
        f"{'loaded' if p['config_loaded'] else 'NOT loaded'} | "
        f"router: {p['router_profile']} | accept: {p['accept_mode']} | "
        f"watchdog: {p['watchdog_authority']}\n{board}"
    )


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


def _cli_handler(args):
    sub = getattr(args, "subcommand", None) or "status"
    if sub == "watchdog":
        from .reports import stage_for
        from .watchdog_logic import find_stalled

        cfg = load_suite_config()
        wd = cfg.get("watchdog") or {}
        tasks = board_tasks()
        reports = board_reports()
        for t in tasks:
            if t.get("status") in ("done", "archived"):
                continue
            stage = stage_for(
                latest_report=reports.get(t.get("id")),
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
