"""Structured worker reports and the task stage table.

Pure logic, no Hermes imports — unit-testable in isolation. Adapted from
dsh-superagent-prototype's Report taxonomy and stage table: a worker's
state is communicated through a small enum, never inferred from free
text, and a task's stage is *derived* from facts (latest report,
attention open, assignment state) instead of being stored and drifting.

Report convention on the Kanban board: a worker MAY leave a board
comment whose first line is machine-readable —

    SA-REPORT: <kind>

followed by free-text detail for humans. Kinds:

  progress — work is under way (also the implicit default)
  waiting  — turn finished, nothing outstanding; a new input resumes it
  ready    — result is ready for a person to review or use
  blocked  — cannot continue without a person (say why, and ask ONE
             concrete question in the detail)
  failed   — the attempt failed (say what failed, plainly)
  dropped  — no work to do / not reproducible / superseded: ends quietly

The SA-REPORT comment is an optional upgrade, never the only source of
truth: `derive_report` prefers it when present, and otherwise derives
the kind from the board's native records (task status + the
`task_events` stream written by kanban_complete / kanban_block / the
dispatcher). Field experience (2026-11-01, first live install) is the
reason: a dispatcher-spawned worker completed its card through the
native handoff — completion summary + artifacts — without ever loading
the skill that teaches SA-REPORT. A reporting layer that depends on a
model voluntarily loading a skill is a reporting layer that silently
has no data; the native records are always there.
"""
import re

REPORT_KINDS = ("progress", "waiting", "ready", "blocked", "failed", "dropped")

_REPORT_RE = re.compile(r"^\s*SA-REPORT:\s*([A-Za-z]+)", re.IGNORECASE | re.MULTILINE)


def parse_report(text):
    """Return the report kind from a board comment, or None."""
    if not text:
        return None
    match = _REPORT_RE.search(text)
    if not match:
        return None
    kind = match.group(1).lower()
    return kind if kind in REPORT_KINDS else None


# Native board event types that conclude a run, mapped to report kinds.
_EVENT_KINDS = {
    "completed": "ready",
    "complete": "ready",
    "blocked": "blocked",
    "gave_up": "failed",
    "failed": "failed",
    "crashed": "failed",
    "timed_out": "failed",
}

# Event types that start a (new) run: a terminal event older than one of
# these belongs to a previous attempt and must not speak for the task now.
_RUN_START_EVENTS = {"created", "claimed", "spawned", "reopened", "unblocked"}


def derive_report(status=None, events=None, sa_report=None):
    """Best available report kind for a task.

    Priority: an explicit SA-REPORT comment wins; else the latest
    run-concluding native event (completed / blocked / gave_up / …);
    else the task's own status. `events` is a chronological list of
    dicts with a `type` key, as read from the board's event table.
    Returns None when nothing meaningful can be said (e.g. a card that
    is merely queued).
    """
    if sa_report in REPORT_KINDS:
        return sa_report
    for event in reversed(list(events or [])):
        etype = str((event or {}).get("type") or "").strip().lower()
        if etype in _EVENT_KINDS:
            return _EVENT_KINDS[etype]
        if etype in _RUN_START_EVENTS:
            break
    status = str(status or "").strip().lower()
    if status == "done":
        return "ready"
    if status == "blocked":
        return "blocked"
    if status == "archived":
        return "dropped"
    if status in ("running", "in_progress"):
        return "progress"
    return None


def stage_for(
    *,
    latest_report=None,
    has_attention=False,
    has_assignment=True,
    delivery_failed=False,
    human_replied_since_report=False,
):
    """Derive a task's stage from facts. First matching row wins.

    Stages name what the task is waiting for:
      person/* — it cannot continue without a human
      working/* — the system owes it work
      idle      — finished its turn; a follow-up can resume it
    """
    if delivery_failed:
        return "person/delivery"
    if has_attention:
        return "person/answer"
    if latest_report == "ready":
        return "person/review"
    if latest_report in ("blocked", "failed") and not human_replied_since_report:
        return f"person/{latest_report}"
    if not has_assignment:
        return "working/queued"
    if latest_report == "waiting":
        return "idle"
    return "working"
