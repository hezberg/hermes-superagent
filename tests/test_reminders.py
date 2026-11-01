import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))

from superagent import reminders as rm  # noqa: E402

NOW = 1_000_000.0


def task(tid, status, title=None, updated=None, assignee="sa-worker-general"):
    return {
        "id": tid,
        "title": title or tid,
        "status": status,
        "assignee": assignee,
        "updated_at": updated,
        "last_heartbeat": None,
    }


def ev(etype, ts):
    return {"type": etype, "ts": ts, "summary": None, "artifacts": []}


class TestStateSince(unittest.TestCase):
    def test_blocked_uses_latest_blocked_event(self):
        t = task("t1", "blocked", updated=NOW - 50)
        events = [ev("created", NOW - 900), ev("blocked", NOW - 300),
                  ev("blocked", NOW - 200)]
        self.assertEqual(rm.state_since_for(t, events), NOW - 200)

    def test_falls_back_to_updated_at(self):
        t = task("t1", "done", updated=NOW - 50)
        self.assertEqual(rm.state_since_for(t, []), NOW - 50)


class TestCandidates(unittest.TestCase):
    def setUp(self):
        self.settings = dict(rm.DEFAULTS)

    def test_blocked_is_now_urgency(self):
        t = task("t1", "blocked", updated=NOW - 100)
        cands = rm.candidates([t], {}, set(), self.settings, NOW)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["kind"], "blocked")
        self.assertEqual(cands[0]["urgency"], "now")

    def test_ready_respects_grace(self):
        fresh = task("t1", "done", updated=NOW - 60)
        old = task("t2", "done", updated=NOW - 5 * 3600)
        cands = rm.candidates([fresh, old], {}, set(), self.settings, NOW)
        self.assertEqual([c["task_id"] for c in cands], ["t2"])
        self.assertEqual(cands[0]["urgency"], "batch")

    def test_stalled_only_for_running_in_stalled_set(self):
        t = task("t1", "running", updated=NOW - 7200)
        self.assertEqual(rm.candidates([t], {}, set(), self.settings, NOW), [])
        cands = rm.candidates([t], {}, {"t1"}, self.settings, NOW)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["kind"], "stalled")

    def test_archived_and_open_states_skipped(self):
        tasks = [task("t1", "archived", updated=NOW - 99999),
                 task("t2", "ready", updated=NOW - 99999),
                 task("t3", "todo", updated=NOW - 99999)]
        self.assertEqual(rm.candidates(tasks, {}, set(), self.settings, NOW), [])


class TestBackoff(unittest.TestCase):
    def setUp(self):
        self.settings = dict(rm.DEFAULTS)

    def test_delay_progression_and_cap(self):
        self.assertEqual(rm.next_delay(0, self.settings), 0)
        self.assertEqual(rm.next_delay(1, self.settings), 3600)
        self.assertEqual(rm.next_delay(2, self.settings), 7200)
        self.assertEqual(rm.next_delay(3, self.settings), 14400)
        self.assertEqual(rm.next_delay(99, self.settings), 24 * 3600)

    def test_filter_due_unseen_then_backoff_then_due_again(self):
        cand = {"task_id": "t1", "kind": "blocked",
                "fingerprint": "t1|blocked|100", "title": "t1"}
        state = {"rows": []}
        due = rm.filter_due([cand], state, self.settings, NOW)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["count"], 0)
        state = {"rows": [{"fingerprint": cand["fingerprint"], "count": 1,
                           "last_at": NOW - 100}]}
        self.assertEqual(rm.filter_due([cand], state, self.settings, NOW), [])
        state["rows"][0]["last_at"] = NOW - 3700
        due = rm.filter_due([cand], state, self.settings, NOW)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["count"], 1)

    def test_state_change_rearms(self):
        old = {"task_id": "t1", "kind": "blocked",
               "fingerprint": "t1|blocked|100", "title": "t1"}
        new = dict(old, fingerprint="t1|blocked|5000")
        state = {"rows": [{"fingerprint": old["fingerprint"], "count": 3,
                           "last_at": NOW - 10}]}
        due = rm.filter_due([new], state, self.settings, NOW)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["count"], 0)


class TestLedger(unittest.TestCase):
    def test_record_prune_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = rm.ReminderLedger(os.path.join(tmp, "reminders.json"))
            due = [{"task_id": "t1", "kind": "blocked",
                    "fingerprint": "t1|blocked|100", "count": 0}]
            ledger.record(due, NOW)
            ledger.record(due, NOW + 10)
            rows = ledger.load()["rows"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["count"], 2)
            ledger.prune(["someone-else"])
            self.assertEqual(ledger.load()["rows"], [])


class TestTickOutput(unittest.TestCase):
    def test_empty_is_silent(self):
        self.assertEqual(rm.format_tick_output([]), "")

    def test_now_lines_and_batch_folded(self):
        due = [
            {"title": "修 bug", "kind": "blocked", "urgency": "now",
             "assignee": "sa-worker-general", "count": 0},
            {"title": "写简报", "kind": "ready", "urgency": "batch",
             "assignee": "sa-worker-research", "count": 0},
            {"title": "做调研", "kind": "ready", "urgency": "batch",
             "assignee": "sa-worker-research", "count": 0},
        ]
        out = rm.format_tick_output(due)
        self.assertIn("修 bug", out)
        self.assertIn("is blocked", out)
        self.assertEqual(out.count("awaiting your review"), 1)  # batch folded to one line
        self.assertIn("写简报", out)


if __name__ == "__main__":
    unittest.main()
