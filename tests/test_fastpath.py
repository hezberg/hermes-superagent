import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))

from superagent.fastpath import classify

RULES = [
    {"pattern": r"^/status\b", "action": "passthrough"},
    {"pattern": r"^ping$", "action": "drop"},
]


class TestFastpath(unittest.TestCase):
    def test_passthrough_match(self):
        self.assertEqual(classify("/status please", RULES), "passthrough")

    def test_drop_match(self):
        self.assertEqual(classify("ping", RULES), "drop")

    def test_default_slowpath(self):
        self.assertEqual(classify("please research X for me", RULES), "slowpath")

    def test_empty_text(self):
        self.assertEqual(classify("", RULES), "slowpath")
        self.assertEqual(classify(None, RULES), "slowpath")

    def test_broken_regex_is_skipped(self):
        rules = [{"pattern": "([", "action": "drop"}, {"pattern": "ok", "action": "drop"}]
        self.assertEqual(classify("ok go", rules), "drop")

    def test_unknown_action_falls_back(self):
        rules = [{"pattern": "x", "action": "explode"}]
        self.assertEqual(classify("x", rules), "slowpath")

    def test_no_rules(self):
        self.assertEqual(classify("anything", []), "slowpath")
        self.assertEqual(classify("anything", None), "slowpath")


if __name__ == "__main__":
    unittest.main()
