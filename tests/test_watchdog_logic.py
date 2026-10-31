import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))

from superagent.watchdog_logic import find_stalled

NOW = 1_700_000_000


def task(**kw):
    base = {"id": "t1", "status": "running", "assignee": "sa-worker-general",
            "updated_at": NOW, "last_heartbeat": NOW}
    base.update(kw)
    return base


class TestWatchdogLogic(unittest.TestCase):
    def test_fresh_task_is_fine(self):
        self.assertEqual(find_stalled([task()], NOW), [])

    def test_no_progress_flagged(self):
        findings = find_stalled([task(updated_at=NOW - 31 * 60)], NOW)
        self.assertEqual(len(findings), 1)
        self.assertIn("no_progress", findings[0]["reasons"])

    def test_stale_heartbeat_flagged(self):
        findings = find_stalled([task(last_heartbeat=NOW - 16 * 60)], NOW)
        self.assertEqual(len(findings), 1)
        self.assertIn("heartbeat_stale", findings[0]["reasons"])

    def test_both_reasons(self):
        findings = find_stalled(
            [task(updated_at=NOW - 3600, last_heartbeat=NOW - 3600)], NOW
        )
        self.assertEqual(sorted(findings[0]["reasons"]),
                         ["heartbeat_stale", "no_progress"])

    def test_non_running_ignored(self):
        old = NOW - 10_000
        tasks = [task(status="done", updated_at=old, last_heartbeat=old),
                 task(status="blocked", updated_at=old, last_heartbeat=old)]
        self.assertEqual(find_stalled(tasks, NOW), [])

    def test_missing_timestamps_never_flag(self):
        t = task(updated_at=None, last_heartbeat=None)
        self.assertEqual(find_stalled([t], NOW), [])

    def test_thresholds_respected(self):
        t = task(updated_at=NOW - 29 * 60, last_heartbeat=NOW - 14 * 60)
        self.assertEqual(find_stalled([t], NOW), [])


if __name__ == "__main__":
    unittest.main()
