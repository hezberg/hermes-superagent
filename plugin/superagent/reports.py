"""Structured worker reports and the task stage table.

Pure logic, no Hermes imports — unit-testable in isolation. Adapted from
dsh-superagent-prototype's Report taxonomy and stage table: a worker's
state is communicated through a small enum, never inferred from free
text, and a task's stage is *derived* from facts (latest report,
attention open, assignment state) instead of being stored and drifting.

Report convention on the Kanban board: the worker's latest board comment
carries a machine-readable first line

    SA-REPORT: <kind>

followed by free-text detail for humans. Kinds:

  progress — work is under way (also the implicit default)
  waiting  — turn finished, nothing outstanding; a new input resumes it
  ready    — result is ready for a person to review or use
  blocked  — cannot continue without a person (say why, and ask ONE
             concrete question in the detail)
  failed   — the attempt failed (say what failed, plainly)
  dropped  — no work to do / not reproducible / superseded: ends quietly
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
