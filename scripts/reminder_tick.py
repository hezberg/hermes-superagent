#!/usr/bin/env python3
"""superagent reminder tick — run by Hermes cron in no-agent mode.

In no-agent mode the script's stdout IS the delivery: Hermes' cron
delivery router sends printed lines verbatim to the user's messaging
platform, and a tick that prints nothing stays silent. That silence
is the common case and the whole point: the ledger guarantees a tick
only speaks when an unclosed task genuinely needs the person.

One tick: sync the journal (finished work becomes memory), detect
stalls, run the ledger-governed reminder pass, print what is due.

Delivery setup (once, by the operator or guided by SETUP.md):
  hermes cron create "every 10m" --no-agent \
      --script superagent-reminder-tick.py --deliver <your platform>

The install script renders __HERMES_HOME__ below to the real path.
"""
import os
import sys
import time

HERMES_HOME = "__HERMES_HOME__"


def main():
    home = os.environ.get("HERMES_HOME") or HERMES_HOME
    sys.path.insert(0, os.path.join(home, "plugins"))
    try:
        import superagent as sa
        from superagent.reminders import format_tick_output
        from superagent.watchdog_logic import find_stalled
    except Exception:
        return 0  # suite not importable: stay silent, never spam errors

    try:
        sa.sync_journal()
        cfg = sa.load_suite_config()
        wd = cfg.get("watchdog") or {}
        tasks = sa.board_tasks()
        events = sa.board_events()
        findings = find_stalled(
            tasks,
            time.time(),
            stall_minutes=wd.get("stall_minutes", 30),
            heartbeat_stale_minutes=wd.get("heartbeat_stale_minutes", 15),
        )
        due = sa.run_reminder_pass(
            tasks, events, {f["task_id"] for f in findings}, wd
        )
        out = format_tick_output(due)
        if out:
            print(out)
    except Exception:
        return 0  # a broken tick must never become a broken record
    return 0


if __name__ == "__main__":
    sys.exit(main())
