import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))

from superagent.reports import derive_report, parse_report, stage_for


class TestParseReport(unittest.TestCase):
    def test_parses_first_line(self):
        self.assertEqual(parse_report("SA-REPORT: ready\nResult is in /tmp/x"), "ready")

    def test_case_insensitive(self):
        self.assertEqual(parse_report("sa-report: Blocked\nneed a decision"), "blocked")

    def test_unknown_kind_ignored(self):
        self.assertIsNone(parse_report("SA-REPORT: vibes\ngoing great"))

    def test_no_marker(self):
        self.assertIsNone(parse_report("just a normal comment"))
        self.assertIsNone(parse_report(""))
        self.assertIsNone(parse_report(None))


class TestStageFor(unittest.TestCase):
    def test_delivery_failure_first(self):
        self.assertEqual(
            stage_for(delivery_failed=True, latest_report="ready"), "person/delivery"
        )

    def test_attention(self):
        self.assertEqual(stage_for(has_attention=True), "person/answer")

    def test_ready_needs_review(self):
        self.assertEqual(stage_for(latest_report="ready"), "person/review")

    def test_blocked_until_human_replies(self):
        self.assertEqual(stage_for(latest_report="blocked"), "person/blocked")
        self.assertEqual(
            stage_for(latest_report="blocked", human_replied_since_report=True),
            "working",
        )

    def test_failed_stage(self):
        self.assertEqual(stage_for(latest_report="failed"), "person/failed")

    def test_queued_without_assignment(self):
        self.assertEqual(stage_for(has_assignment=False), "working/queued")

    def test_waiting_is_idle(self):
        self.assertEqual(stage_for(latest_report="waiting"), "idle")

    def test_default_working(self):
        self.assertEqual(stage_for(), "working")
        self.assertEqual(stage_for(latest_report="progress"), "working")


def ev(*types):
    return [{"type": t} for t in types]


class TestDeriveReport(unittest.TestCase):
    def test_sa_report_wins(self):
        self.assertEqual(
            derive_report("done", ev("completed"), sa_report="blocked"), "blocked"
        )

    def test_completed_event_is_ready(self):
        # Real shape from a live board: completed is followed by a
        # non-terminal worker_result event.
        self.assertEqual(
            derive_report("done", ev("created", "claimed", "completed", "worker_result")),
            "ready",
        )

    def test_blocked_event(self):
        self.assertEqual(derive_report("blocked", ev("claimed", "blocked")), "blocked")

    def test_gave_up_is_failed(self):
        self.assertEqual(derive_report("blocked", ev("claimed", "gave_up")), "failed")

    def test_reopened_task_ignores_old_completion(self):
        # completed in run 1, claimed again in run 2: the old terminal
        # event must not speak for the new run; status fallback applies.
        self.assertEqual(
            derive_report("running", ev("completed", "claimed", "spawned")),
            "progress",
        )

    def test_status_fallbacks(self):
        self.assertEqual(derive_report("done"), "ready")
        self.assertEqual(derive_report("blocked"), "blocked")
        self.assertEqual(derive_report("archived"), "dropped")
        self.assertEqual(derive_report("running"), "progress")

    def test_queued_card_says_nothing(self):
        self.assertIsNone(derive_report("ready", ev("created")))
        self.assertIsNone(derive_report("triage"))
        self.assertIsNone(derive_report(None, None, None))


if __name__ == "__main__":
    unittest.main()
