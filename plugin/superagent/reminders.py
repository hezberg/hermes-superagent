"""Reminder ledger: proactive nudges for work that has not closed.

The discipline (docs/PRINCIPLES.md #6 — proactive beats queryable),
modeled on how a good assistant actually reminds:

- A *situation* is a task in a state that needs the person: blocked,
  finished-but-unreviewed ("ready"), or running-but-silent
  ("stalled"). It is identified by a fingerprint — task + kind + the
  epoch it entered that state — so the same situation is never
  re-announced as if it were new.
- Each situation is surfaced at most once per backoff window: the
  first nudge comes after a grace period in the state, later nudges
  wait twice as long each time (capped). Ignored work nags *less*
  over time, not more.
- A state change re-arms: a new fingerprint starts a fresh cycle.
- Closed tasks are pruned from the ledger; their rows never speak
  again.

Facts only: this module decides *whether* a nudge is due and renders
its one-line prose. Judgement about tone and timing in conversation
stays with the Router (see the router skill's reminder protocol).

Storage mirrors the outbox: one JSON file, load/mutate/save, atomic
via rename. Volumes are human-scale.
"""
import json
import os

DEFAULTS = {
    "blocked_after_minutes": 0,      # a fresh block is news right away
    "ready_after_minutes": 240,      # finished work can wait for review
    "stalled_after_minutes": 0,      # stall detection already has grace
    "backoff_cap_minutes": 24 * 60,  # never wait longer than a day
    "backoff_base_minutes": 60,      # first re-nudge after an hour
}


def fingerprint(task_id, kind, state_since):
    return f"{task_id}|{kind}|{int(state_since or 0)}"


def settings_from(watchdog_cfg):
    """Reminder knobs live in the suite config's watchdog section as
    `remind_*` keys; anything unset falls back to DEFAULTS."""
    wd = watchdog_cfg or {}
    out = dict(DEFAULTS)
    for key in DEFAULTS:
        value = wd.get("remind_" + key)
        if isinstance(value, (int, float)) and value >= 0:
            out[key] = value
    return out


def state_since_for(task, events):
    """Epoch at which the task entered its current state: the latest
    run-state event at or after the last run start. Falls back to the
    row's updated_at. Event `ts` values are epoch seconds, as provided
    by board_events()."""
    status = str(task.get("status") or "")
    wanted = {
        "blocked": {"blocked"},
        "done": {"completed"},
        "running": {"claimed", "spawned", "created"},
        "in_progress": {"claimed", "spawned", "created"},
    }.get(status, set())
    best = None
    for event in events or []:
        etype = str((event or {}).get("type") or "").strip().lower()
        ts = (event or {}).get("ts")
        if etype in wanted and isinstance(ts, (int, float)):
            if best is None or ts > best:
                best = ts
    if best is not None:
        return best
    updated = task.get("updated_at")
    return updated if isinstance(updated, (int, float)) else None


def candidates(tasks, events_by_task, stalled_ids, settings, now):
    """Situations worth surfacing, before ledger filtering.

    Returns dicts: task_id, title, assignee, kind, urgency
    ("now" = may interrupt, "batch" = next conversation opening),
    state_since, summary (for ready cards, when known).
    """
    out = []
    stalled_ids = stalled_ids or set()
    for task in tasks or []:
        if not isinstance(task, dict):
            continue
        status = str(task.get("status") or "")
        task_id = task.get("id")
        if status in ("archived",):
            continue
        events = (events_by_task or {}).get(task_id)
        kind = urgency = None
        if status == "blocked":
            kind, urgency = "blocked", "now"
        elif status == "done":
            kind, urgency = "ready", "batch"
        elif task_id in stalled_ids:
            kind, urgency = "stalled", "now"
        if kind is None:
            continue
        since = state_since_for(task, events)
        if since is None:
            continue
        grace = settings.get(kind + "_after_minutes", 0) * 60
        if now - since < grace:
            continue
        out.append(
            {
                "task_id": task_id,
                "title": task.get("title") or task_id,
                "assignee": task.get("assignee"),
                "kind": kind,
                "urgency": urgency,
                "state_since": since,
                "fingerprint": fingerprint(task_id, kind, since),
            }
        )
    return out


def next_delay(count, settings):
    """Seconds to wait before re-nudging a situation already surfaced
    `count` times: base × 2^(count-1), capped."""
    base = settings.get("backoff_base_minutes", 60) * 60
    cap = settings.get("backoff_cap_minutes", 24 * 60) * 60
    if count <= 0:
        return 0
    return min(base * (2 ** (count - 1)), cap)


def filter_due(cands, ledger_state, settings, now):
    """Attach ledger state: a candidate is due when its fingerprint is
    unseen, or its backoff window has elapsed."""
    rows = {r["fingerprint"]: r for r in (ledger_state or {}).get("rows", [])}
    due = []
    for cand in cands or []:
        row = rows.get(cand["fingerprint"])
        count = int(row.get("count", 0)) if row else 0
        if row is not None:
            last = row.get("last_at") or 0
            if now - last < next_delay(count, settings):
                continue
        due.append(dict(cand, count=count))
    return due


_KIND_PROSE = {
    "blocked": "卡住了，在等你回话",
    "ready": "已完成，等你验收",
    "stalled": "在跑，但已经好一会儿没动静了",
}


def render_reminder_lines(due):
    """One prose line per due reminder — the text a person reads."""
    lines = []
    for cand in due or []:
        who = cand.get("assignee") or "worker"
        suffix = "（已提醒过 {} 次）".format(cand["count"]) if cand.get("count") else ""
        lines.append(
            "⏰ 「{}」{}（{}）{}".format(
                cand["title"], _KIND_PROSE.get(cand["kind"], cand["kind"]),
                who, suffix,
            )
        )
    return lines


def format_tick_output(due):
    """What a cron tick prints (and therefore delivers). Urgent items
    get their own line each; finished-but-unreviewed items fold into a
    single gentle summary line. Nothing due → empty string → the tick
    stays silent."""
    due = due or []
    now_items = [c for c in due if c.get("urgency") == "now"]
    batch = [c for c in due if c.get("urgency") != "now"]
    lines = render_reminder_lines(now_items)
    if batch:
        titles = "、".join("「{}」".format(c["title"]) for c in batch[:3])
        more = " 等 {} 件".format(len(batch)) if len(batch) > 3 else ""
        lines.append(
            "📋 另有已完成、待你验收的任务：{}{}——细节在看板和 journal 里。".format(
                titles, more
            )
        )
    return "\n".join(lines)


class ReminderLedger:
    """Ledger of surfaced situations, same storage pattern as Outbox."""

    def __init__(self, path):
        self.path = path

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                state = json.load(fh)
            if isinstance(state, dict) and isinstance(state.get("rows"), list):
                return state
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return {"rows": []}

    def _save(self, state):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def record(self, due, now):
        """Mark each due candidate as surfaced at `now`."""
        state = self.load()
        by_fp = {r["fingerprint"]: r for r in state["rows"]}
        for cand in due or []:
            row = by_fp.get(cand["fingerprint"])
            if row is None:
                row = {
                    "fingerprint": cand["fingerprint"],
                    "task_id": cand["task_id"],
                    "kind": cand["kind"],
                    "count": 0,
                    "first_at": now,
                    "last_at": now,
                }
                state["rows"].append(row)
                by_fp[cand["fingerprint"]] = row
            row["count"] = int(row.get("count", 0)) + 1
            row["last_at"] = now
        self._save(state)
        return state

    def prune(self, open_fingerprints):
        """Drop rows for situations that no longer exist."""
        keep = set(open_fingerprints or [])
        state = self.load()
        state["rows"] = [r for r in state["rows"] if r["fingerprint"] in keep]
        self._save(state)
        return state
