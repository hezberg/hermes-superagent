"""Suite journal: the durable, cross-task memory of finished work.

Every terminal card yields one journal entry — what was asked, who did
it, how it ended, the outcome summary, and where the artifacts live.
The journal is the suite's *global* memory: it is what lets the Router
answer "what happened with X?" next week without polling the board,
and what a morning digest is rendered from.

This exists because the design it borrows from has no such layer: in
dsh-superagent-prototype, a ticket's completion stays inside that
ticket's repo-scoped record and never becomes shared memory. Hermes'
habitat is a person's ongoing life with their agent; outcomes have to
accumulate somewhere the next conversation can read.

Storage (written by the plugin, in $HERMES_HOME/superagent/):
  journal.jsonl — append-only machine record
  journal.md    — the same entries, rendered for humans

Pure logic, no Hermes imports. Sync is idempotent: an entry is keyed
by (task_id, terminal moment), so re-running a sync never duplicates.
"""
from datetime import datetime

# Run-concluding board events and the journal outcome they record.
OUTCOME_BY_EVENT = {
    "completed": "ready",
    "complete": "ready",
    "blocked": "blocked",
    "gave_up": "failed",
    "crashed": "failed",
    "timed_out": "failed",
    "failed": "failed",
}

_RUN_START_EVENTS = {"created", "claimed", "spawned", "reopened", "unblocked"}

# Task statuses that mean "this card is finished" on their own.
_TERMINAL_STATUS_OUTCOME = {"done": "ready", "blocked": "blocked", "archived": "dropped"}

OUTCOME_WORDS = {
    "ready": "done",
    "blocked": "blocked",
    "failed": "failed",
    "dropped": "archived",
}


def entry_key(entry):
    return f"{entry.get('task_id')}@{entry.get('ts')}"


def _terminal_event(events):
    """Latest run-concluding event of the latest run, or None."""
    for event in reversed(list(events or [])):
        etype = str((event or {}).get("type") or "").strip().lower()
        if etype in OUTCOME_BY_EVENT:
            return event
        if etype in _RUN_START_EVENTS:
            return None
    return None


def new_entries(tasks, events_by_task, seen_keys):
    """Journal entries for terminal tasks not yet journaled.

    `tasks` are board task dicts (id, title, status, assignee,
    updated_at); `events_by_task` maps task id to its chronological
    board events (dicts with type/ts, optionally summary/artifacts on
    the concluding event). Returns entries in task order.
    """
    entries = []
    for task in tasks or []:
        task_id = task.get("id")
        if not task_id:
            continue
        events = (events_by_task or {}).get(task_id) or []
        term = _terminal_event(events)
        status = str(task.get("status") or "").strip().lower()
        if term is not None:
            etype = str(term.get("type") or "").strip().lower()
            outcome = OUTCOME_BY_EVENT[etype]
            ts = term.get("ts") or task.get("updated_at")
            summary = term.get("summary") or ""
            artifacts = term.get("artifacts") or []
        elif status in _TERMINAL_STATUS_OUTCOME:
            outcome = _TERMINAL_STATUS_OUTCOME[status]
            ts = task.get("updated_at")
            summary = ""
            artifacts = []
        else:
            continue
        entry = {
            "task_id": task_id,
            "title": task.get("title") or task_id,
            "assignee": task.get("assignee"),
            "outcome": outcome,
            "ts": ts,
            "summary": summary,
            "artifacts": list(artifacts),
        }
        if entry_key(entry) not in (seen_keys or set()):
            entries.append(entry)
    return entries


def _fmt_ts(ts):
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return "unknown time"


def _one_line(text, limit=160):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_digest(entries, limit=8):
    """Prose digest of the most recent outcomes, for chat surfaces."""
    recent = list(entries or [])[-limit:]
    if not recent:
        return "No finished tasks recorded yet."
    lines = ["Recent task outcomes:"]
    for e in reversed(recent):
        word = OUTCOME_WORDS.get(e.get("outcome"), e.get("outcome") or "")
        who = e.get("assignee") or "unassigned"
        line = f"- [{_fmt_ts(e.get('ts'))}] {e.get('title')} — {who} {word}"
        summary = _one_line(e.get("summary"))
        if summary:
            line += f": {summary}"
        lines.append(line)
    return "\n".join(lines)


def search_entries(entries, query):
    """Entries whose title/summary/assignee/task id mention the query
    (case-insensitive substring). An empty query matches nothing."""
    q = str(query or "").strip().lower()
    if not q:
        return []
    out = []
    for e in entries or []:
        haystack = " ".join(
            str(e.get(k) or "") for k in ("title", "summary", "assignee", "task_id")
        ).lower()
        if q in haystack:
            out.append(e)
    return out


def render_journal_md(entries):
    """The full human-readable journal document."""
    lines = [
        "# Super-agent journal",
        "",
        "A durable record of finished tasks: who did them, how they ended, and where the deliverables are. Maintained automatically by hermes-superagent.",
        "",
    ]
    for e in reversed(list(entries or [])):
        word = OUTCOME_WORDS.get(e.get("outcome"), e.get("outcome") or "")
        lines.append(f"## [{_fmt_ts(e.get('ts'))}] {e.get('title')}")
        lines.append(
            f"- Outcome: {word} | By: {e.get('assignee') or 'unassigned'} | Task: `{e.get('task_id')}`"
        )
        if e.get("summary"):
            lines.append(f"- Summary: {e['summary']}")
        for art in e.get("artifacts") or []:
            lines.append(f"- Artifacts: {art}")
        lines.append("")
    return "\n".join(lines)
