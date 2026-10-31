"""Watchdog stall detection over Kanban task rows.

Pure logic, no Hermes imports — unit-testable in isolation.

A task counts as stalled when it is in `running` state AND either:
  - its board row has not been updated for `stall_minutes`, or
  - its worker heartbeat is older than `heartbeat_stale_minutes`.

Timestamps are epoch seconds. Missing timestamps never produce a finding
on their own (absence of evidence is not evidence of a stall).
"""


def find_stalled(tasks, now, stall_minutes=30, heartbeat_stale_minutes=15):
    findings = []
    stall_after = stall_minutes * 60
    heartbeat_after = heartbeat_stale_minutes * 60
    for task in tasks or []:
        if not isinstance(task, dict) or task.get("status") != "running":
            continue
        reasons = []
        updated_at = task.get("updated_at")
        if isinstance(updated_at, (int, float)) and now - updated_at > stall_after:
            reasons.append("no_progress")
        heartbeat = task.get("last_heartbeat")
        if isinstance(heartbeat, (int, float)) and now - heartbeat > heartbeat_after:
            reasons.append("heartbeat_stale")
        if reasons:
            findings.append(
                {
                    "task_id": task.get("id"),
                    "assignee": task.get("assignee"),
                    "reasons": reasons,
                }
            )
    return findings
