import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))

from superagent import doctor as doc


def levels(findings):
    return [f["level"] for f in findings]


class TestKeyEnv(unittest.TestCase):
    def test_missing_everywhere_is_error_with_fix(self):
        findings = doc.check_key_env(
            {"main": {"api_key_env": "SUPERAGENT_MAIN_API_KEY"}},
            {"SUPERAGENT_MAIN_API_KEY": False},
        )
        self.assertEqual(levels(findings), ["error"])
        self.assertIn(".env", findings[0]["fix"])

    def test_present_is_ok(self):
        findings = doc.check_key_env(
            {"main": {"api_key_env": "K"}}, {"K": True}
        )
        self.assertEqual(levels(findings), ["ok"])


class TestRouterToolsets(unittest.TestCase):
    def test_legacy_agent_toolsets_is_error(self):
        findings = doc.check_router_toolsets(
            "sa-router", {"agent": {"toolsets": ["kanban"]}}
        )
        self.assertEqual(levels(findings), ["error"])

    def test_missing_kanban_is_error(self):
        findings = doc.check_router_toolsets(
            "sa-router", {"platform_toolsets": {"cli": ["memory"]}}
        )
        self.assertEqual(levels(findings), ["error"])
        self.assertIn("tools enable kanban", findings[0]["fix"])

    def test_execution_tools_warn(self):
        findings = doc.check_router_toolsets(
            "sa-router",
            {"platform_toolsets": {"cli": ["kanban", "memory", "skills", "web"]}},
        )
        self.assertEqual(levels(findings), ["warn"])

    def test_clean_router_ok(self):
        findings = doc.check_router_toolsets(
            "sa-router",
            {"platform_toolsets": {"cli": ["kanban", "memory", "skills"]}},
        )
        self.assertEqual(levels(findings), ["ok"])


class TestFakeIp(unittest.TestCase):
    def test_range_boundaries(self):
        self.assertTrue(doc.is_fake_ip("198.18.0.1"))
        self.assertTrue(doc.is_fake_ip("198.19.255.255"))
        self.assertFalse(doc.is_fake_ip("198.20.0.1"))
        self.assertFalse(doc.is_fake_ip("8.8.8.8"))
        self.assertFalse(doc.is_fake_ip("not-an-ip"))

    def test_blocked_profiles_error_names_them(self):
        findings = doc.check_fake_ip(
            ["198.18.4.182"], {"sa-router": True, "sa-worker-research": False}
        )
        self.assertEqual(levels(findings), ["error"])
        self.assertIn("sa-worker-research", findings[0]["text"])

    def test_all_allowed_ok_and_no_fake_no_finding(self):
        self.assertEqual(
            levels(doc.check_fake_ip(["198.18.0.9"], {"a": True})), ["ok"]
        )
        self.assertEqual(doc.check_fake_ip(["1.1.1.1"], {"a": False}), [])


class TestMisc(unittest.TestCase):
    def test_private_base_url_warns_but_allows(self):
        findings = doc.check_private_base_url(
            {"main": {"base_url": "http://100.64.0.1:3001/v1"}}
        )
        self.assertEqual(levels(findings), ["warn"])
        self.assertEqual(doc.check_private_base_url(
            {"main": {"base_url": "https://api.deepseek.com"}}), [])

    def test_smart_quotes_error(self):
        findings = doc.check_smart_quotes({"sa-router": 'provider: “custom”'})
        self.assertEqual(levels(findings), ["error"])
        self.assertEqual(doc.check_smart_quotes({"sa-router": 'provider: "custom"'}), [])

    def test_board_absent_warns(self):
        self.assertEqual(levels(doc.check_board(None)), ["warn"])
        self.assertEqual(levels(doc.check_board({"done": 2})), ["ok"])

    def test_summarize_counts(self):
        findings = [{"level": "error", "text": "x"}, {"level": "warn", "text": "y"}]
        self.assertIn("1 个问题", doc.summarize(findings))
        self.assertIn("全部正常", doc.summarize([{"level": "ok", "text": "z"}]))


if __name__ == "__main__":
    unittest.main()
