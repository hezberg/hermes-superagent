import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))

from superagent.gate import (
    accept_mode,
    evaluate,
    make_mandate,
    mandate_block,
    policy_version,
)

POLICY = {
    "accept_mode": "observe",
    "sources": {
        "cli": {"allowed_senders": []},
        "feishu": {"allowed_senders": ["ou_alice"]},
        "webhook": {"allowed_senders": []},
    },
    "bots": ["ci-bot"],
    "rules": [{"id": "ci-failure", "instruction": "CI failures are worth a fix."}],
}


def event(**kw):
    base = {"source": "feishu", "sender": "ou_alice", "addressed": False,
            "is_stop": False, "is_bot": False, "rule_match": False}
    base.update(kw)
    return base


class TestGateExplicit(unittest.TestCase):
    def test_allowed_and_addressed_accepts(self):
        d = evaluate(event(addressed=True), POLICY)
        self.assertEqual(d["outcome"], "accept")
        self.assertEqual(d["strength"], "explicit")

    def test_cli_operator_always_allowed(self):
        d = evaluate(event(source="cli", sender="whoever", addressed=True), POLICY)
        self.assertEqual(d["outcome"], "accept")

    def test_stranger_addressed_is_rejected(self):
        d = evaluate(event(sender="ou_mallory", addressed=True), POLICY)
        self.assertEqual(d["outcome"], "reject")
        self.assertIsNone(d["strength"])

    def test_empty_allowlist_rejects_everyone(self):
        d = evaluate(event(source="webhook", sender="tok1", addressed=True), POLICY)
        self.assertEqual(d["outcome"], "reject")

    def test_stop_from_allowed_wins(self):
        d = evaluate(event(is_stop=True), POLICY)
        self.assertEqual(d["outcome"], "stop")
        self.assertEqual(d["strength"], "explicit")

    def test_stop_from_stranger_is_not_a_stop(self):
        d = evaluate(event(sender="ou_mallory", is_stop=True), POLICY)
        self.assertNotEqual(d["outcome"], "stop")


class TestGateInferred(unittest.TestCase):
    def test_rule_match_observes_by_default(self):
        d = evaluate(event(sender="ou_bob", rule_match=True, rule_id="ci-failure"), POLICY)
        self.assertEqual(d["outcome"], "observe")
        self.assertEqual(d["strength"], "inferred")
        self.assertEqual(d["basis"]["rule_id"], "ci-failure")

    def test_rule_match_accepts_in_auto_mode(self):
        policy = dict(POLICY, accept_mode="auto")
        d = evaluate(event(sender="ou_bob", rule_match=True), policy)
        self.assertEqual(d["outcome"], "accept")

    def test_listed_bot_raises_candidate(self):
        d = evaluate(event(sender="ci-bot", is_bot=True), POLICY)
        self.assertEqual(d["outcome"], "observe")
        self.assertEqual(d["basis"]["via"], "bot")

    def test_unlisted_bot_is_ignored(self):
        d = evaluate(event(sender="random-bot", is_bot=True), POLICY)
        self.assertEqual(d["outcome"], "ignore")

    def test_plain_chatter_is_ignored(self):
        d = evaluate(event(sender="ou_bob"), POLICY)
        self.assertEqual(d["outcome"], "ignore")


class TestPolicyVersionAndMode(unittest.TestCase):
    def test_version_stable_and_sensitive(self):
        self.assertEqual(policy_version(POLICY), policy_version(dict(POLICY)))
        changed = dict(POLICY, accept_mode="auto")
        self.assertNotEqual(policy_version(POLICY), policy_version(changed))

    def test_accept_mode_defaults_observe(self):
        self.assertEqual(accept_mode({}), "observe")
        self.assertEqual(accept_mode(None, {"speculative_execution": True}), "auto")
        self.assertEqual(accept_mode({"accept_mode": "auto"}, None), "auto")

    def test_mandate_block_contents(self):
        m = make_mandate(POLICY, source="feishu", sender="ou_alice",
                         strength="explicit", scope="fix the typo",
                         basis={"via": "addressed"}, now=123)
        block = mandate_block(m)
        self.assertIn(policy_version(POLICY), block)
        self.assertIn("explicit", block)
        self.assertIn("fix the typo", block)
        self.assertEqual(m["accepted_at"], 123)


if __name__ == "__main__":
    unittest.main()
