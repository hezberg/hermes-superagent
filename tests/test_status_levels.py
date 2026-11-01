import os
import sqlite3
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))


class TestStatusLevels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.tmp.name
        now = int(time.time())
        db = sqlite3.connect(os.path.join(self.tmp.name, "kanban.db"))
        db.execute(
            "CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, body TEXT,"
            " assignee TEXT, status TEXT, priority INTEGER, created_by TEXT,"
            " created_at INTEGER, started_at INTEGER, completed_at INTEGER,"
            " result TEXT, consecutive_failures INTEGER)")
        db.execute(
            "CREATE TABLE task_links (parent_id TEXT, child_id TEXT)")
        rows = [
            ("t_run1", "Research video platforms", "long body about platforms",
             "sa-worker-research", "running", 1, "sa-router", now - 2700,
             now - 2600, None, "", 0),
            ("t_block1", "Book the venue", "needs a human decision",
             "sa-worker-general", "blocked", 2, "sa-router", now - 7200,
             None, None, "", 0),
            ("t_done1", "Summarize the paper", "summarize body",
             "sa-worker-general", "done", 0, "sa-router", now - 90000,
             now - 89000, now - 88000, "Summary delivered: 3 key points.", 0),
            ("t_fail1", "Scrape the site", "scrape body",
             "sa-worker-research", "failed", 0, "sa-router", now - 50000,
             now - 49000, None, "HTTP 403 from the target", 2),
        ]
        db.executemany("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        db.execute("INSERT INTO task_links VALUES ('t_block1', 't_run1')")
        db.commit()
        db.close()
        import superagent
        self.sa = superagent

    def tearDown(self):
        if self.old is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self.old
        self.tmp.cleanup()

    def test_level0_is_compact(self):
        text = self.sa.status_text(0)
        self.assertIn("running=1", text)
        self.assertNotIn("Research video platforms", text)

    def test_level1_shows_the_board(self):
        text = self.sa.status_text(1)
        self.assertIn("Running (1):", text)
        self.assertIn("Research video platforms", text)
        self.assertIn("→ sa-worker-research", text)
        self.assertIn("Blocked (1):", text)
        self.assertIn("Summarize the paper", text)
        # detail stays out at this level
        self.assertNotIn("Summary delivered: 3 key points.", text)
        self.assertNotIn("child of", text)

    def test_level2_adds_detail(self):
        text = self.sa.status_text(2)
        self.assertIn("Summary delivered: 3 key points.", text)
        self.assertIn("HTTP 403 from the target", text)
        self.assertIn("child of t_block1", text)
        self.assertIn("failures 2", text)

    def test_cli_levels(self):
        import argparse
        import contextlib
        import io
        parser = argparse.ArgumentParser()
        self.sa._cli_setup(parser)
        for argv, needle in (
            (["status"], "Research video platforms"),
            (["status", "-v"], "Summary delivered"),
        ):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = self.sa._cli_handler(parser.parse_args(argv))
            self.assertEqual(rc, 0)
            self.assertIn(needle, out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.sa._cli_handler(parser.parse_args(["status", "-q"]))
        self.assertNotIn("Research video platforms", out.getvalue())
