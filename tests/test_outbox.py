import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))

from superagent.outbox import MAX_FAILURES, Outbox


class TestOutbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.box = Outbox(os.path.join(self.tmp.name, "outbox.json"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_in_conversation_is_due_second_waits(self):
        a = self.box.enqueue("t1", "chat-1", "ack")
        b = self.box.enqueue("t1", "chat-1", "result")
        due = [m["id"] for m in self.box.due()]
        self.assertEqual(due, [a])
        self.box.mark_sent(a)
        self.assertEqual([m["id"] for m in self.box.due()], [b])

    def test_other_tickets_do_not_wait(self):
        a = self.box.enqueue("t1", "chat-1", "one")
        c = self.box.enqueue("t2", "chat-1", "two")
        self.assertEqual({m["id"] for m in self.box.due()}, {a, c})

    def test_problem_message_stops_blocking(self):
        a = self.box.enqueue("t1", "chat-1", "ack")
        b = self.box.enqueue("t1", "chat-1", "result")
        for _ in range(MAX_FAILURES):
            self.box.mark_failed(a)
        self.assertEqual([m["id"] for m in self.box.problems()], [a])
        self.assertEqual([m["id"] for m in self.box.due()], [b])

    def test_sent_message_is_not_a_problem(self):
        a = self.box.enqueue("t1", "chat-1", "ack")
        self.box.mark_failed(a)
        self.box.mark_sent(a)
        self.assertEqual(self.box.problems(), [])
        self.assertEqual(self.box.due(), [])

    def test_persists_across_instances(self):
        a = self.box.enqueue("t1", "chat-1", "ack")
        other = Outbox(self.box.path)
        self.assertEqual([m["id"] for m in other.due()], [a])


if __name__ == "__main__":
    unittest.main()
