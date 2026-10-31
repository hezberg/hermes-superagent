import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))

from superagent.journal import entry_key, new_entries, render_digest, render_journal_md


def task(tid, status, title="任务", assignee="sa-worker-research", updated=1000.0):
    return {"id": tid, "title": title, "status": status,
            "assignee": assignee, "updated_at": updated}


def ev(etype, ts, **extra):
    d = {"type": etype, "ts": ts}
    d.update(extra)
    return d


class TestNewEntries(unittest.TestCase):
    def test_completed_card_becomes_ready_entry_with_summary(self):
        tasks = [task("t1", "done", title="查 DeepSeek")]
        events = {"t1": [ev("created", 900.0), ev("claimed", 910.0),
                         ev("completed", 990.0, summary="结论：无新发布",
                            artifacts=["/tmp/brief.md"]),
                         ev("worker_result", 995.0)]}
        entries = new_entries(tasks, events, set())
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["outcome"], "ready")
        self.assertEqual(e["ts"], 990.0)
        self.assertEqual(e["summary"], "结论：无新发布")
        self.assertEqual(e["artifacts"], ["/tmp/brief.md"])
        self.assertEqual(e["title"], "查 DeepSeek")

    def test_gave_up_is_failed_even_when_status_blocked(self):
        tasks = [task("t2", "blocked")]
        events = {"t2": [ev("claimed", 10.0), ev("gave_up", 20.0)]}
        entries = new_entries(tasks, events, set())
        self.assertEqual(entries[0]["outcome"], "failed")

    def test_idempotent_by_key(self):
        tasks = [task("t1", "done")]
        events = {"t1": [ev("completed", 990.0)]}
        first = new_entries(tasks, events, set())
        seen = {entry_key(e) for e in first}
        self.assertEqual(new_entries(tasks, events, seen), [])

    def test_running_and_queued_tasks_produce_nothing(self):
        tasks = [task("t3", "running"), task("t4", "ready")]
        events = {"t3": [ev("claimed", 5.0)], "t4": [ev("created", 5.0)]}
        self.assertEqual(new_entries(tasks, events, set()), [])

    def test_reopened_task_waits_for_latest_run(self):
        # Run 1 completed, run 2 still going: nothing to journal yet.
        tasks = [task("t5", "running")]
        events = {"t5": [ev("completed", 100.0), ev("claimed", 200.0)]}
        self.assertEqual(new_entries(tasks, events, set()), [])
        # Run 2 blocks: journal the block, keyed at the new terminal time.
        events = {"t5": [ev("completed", 100.0), ev("claimed", 200.0),
                         ev("blocked", 300.0)]}
        entries = new_entries(tasks, events, set())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["outcome"], "blocked")
        self.assertEqual(entries[0]["ts"], 300.0)

    def test_status_only_fallback(self):
        entries = new_entries([task("t6", "done", updated=42.0)], {}, set())
        self.assertEqual(entries[0]["outcome"], "ready")
        self.assertEqual(entries[0]["ts"], 42.0)


class TestRender(unittest.TestCase):
    def test_digest_mentions_title_and_outcome(self):
        entries = new_entries(
            [task("t1", "done", title="简报任务")],
            {"t1": [ev("completed", 990.0, summary="已交付")]},
            set(),
        )
        text = render_digest(entries)
        self.assertIn("简报任务", text)
        self.assertIn("完成", text)
        self.assertIn("已交付", text)

    def test_digest_empty(self):
        self.assertIn("还没有", render_digest([]))

    def test_journal_md_lists_artifacts(self):
        entries = new_entries(
            [task("t1", "done")],
            {"t1": [ev("completed", 990.0, artifacts=["/a/b.md"])]},
            set(),
        )
        self.assertIn("/a/b.md", render_journal_md(entries))


if __name__ == "__main__":
    unittest.main()
