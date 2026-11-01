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


class TestPrivateUrls(unittest.TestCase):
    def test_undeclared_setting_means_no_opinion(self):
        self.assertEqual(doc.check_private_urls(None, {"a": False}), [])
        self.assertEqual(doc.check_private_urls(None, {}), [])

    def test_declared_on_but_profile_missing_it_errors(self):
        findings = doc.check_private_urls(
            True, {"sa-router": True, "sa-worker-research": False}
        )
        self.assertEqual(levels(findings), ["error"])
        self.assertIn("sa-worker-research", findings[0]["text"])

    def test_declared_on_and_rendered_everywhere_ok(self):
        self.assertEqual(
            levels(doc.check_private_urls(True, {"a": True})), ["ok"]
        )

    def test_declared_off_but_profile_allows_warns(self):
        findings = doc.check_private_urls(False, {"a": True, "b": False})
        self.assertEqual(levels(findings), ["warn"])
        self.assertIn("a", findings[0]["text"])

    def test_declared_off_and_consistent_is_silent(self):
        self.assertEqual(doc.check_private_urls(False, {"a": False}), [])


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
        self.assertIn("1 problem(s)", doc.summarize(findings))
        self.assertIn("all clear", doc.summarize([{"level": "ok", "text": "z"}]))


class TestPluginEnablement(unittest.TestCase):
    def test_not_in_enabled_list_is_error_with_fix(self):
        findings = doc.check_plugin_enablement(["other-plugin"], [])
        self.assertEqual(levels(findings), ["error"])
        self.assertIn("hermes plugins enable superagent", findings[0]["fix"])

    def test_disabled_wins_is_error(self):
        findings = doc.check_plugin_enablement(["superagent"], ["superagent"])
        self.assertEqual(levels(findings), ["error"])

    def test_enabled_ok(self):
        self.assertEqual(
            levels(doc.check_plugin_enablement(["superagent"], [])), ["ok"])

    def test_no_list_at_all_warns(self):
        self.assertEqual(levels(doc.check_plugin_enablement(None, [])), ["warn"])

    def test_plugin_files_missing_is_error(self):
        self.assertEqual(
            levels(doc.check_plugin_enablement(["superagent"], [], False)),
            ["error"])


class TestInstallDrift(unittest.TestCase):
    def test_version_mismatch_warns(self):
        findings = doc.check_install_drift("0.2.2", "0.3.0", None, None)
        self.assertEqual(levels(findings), ["warn"])

    def test_config_edited_after_install_warns(self):
        findings = doc.check_install_drift("0.3.0", "0.3.0", 2000.0, 1000.0)
        self.assertEqual(levels(findings), ["warn"])
        self.assertEqual(doc.check_install_drift("0.3.0", "0.3.0", 900.0, 1000.0), [])

    def test_no_manifest_no_findings(self):
        self.assertEqual(doc.check_install_drift(None, "0.3.0", None, None), [])


if __name__ == "__main__":
    unittest.main()


class TestKeyConvergence(unittest.TestCase):
    def test_differing_profile_copy_is_an_error(self):
        findings = doc.check_key_convergence(
            {"sa-router": ["SUPERAGENT_MAIN_API_KEY"]})
        self.assertEqual(findings[0]["level"], "error")
        self.assertIn("different", findings[0]["text"])

    def test_converged_is_silent(self):
        self.assertEqual(doc.check_key_convergence({}), [])


class TestPresenceMeansNonEmpty(unittest.TestCase):
    def test_empty_line_is_not_presence(self):
        out = doc.presence_from_env_texts(["KEY=\n"], {})
        self.assertEqual(out, {"KEY": False})

    def test_value_in_any_file_wins(self):
        out = doc.presence_from_env_texts(["KEY=\n", "KEY=sk-x\n"], {})
        self.assertTrue(out["KEY"])
        out = doc.presence_from_env_texts(["KEY=sk-x\n", "KEY=\n"], {})
        self.assertTrue(out["KEY"])

    def test_export_and_quotes_count(self):
        out = doc.presence_from_env_texts(['export KEY="sk-x"\n'], {})
        self.assertTrue(out["KEY"])

    def test_environ_counts_only_non_empty(self):
        out = doc.presence_from_env_texts([], {"A": "1", "B": ""})
        self.assertEqual(out, {"A": True})


class TestEntryWiring(unittest.TestCase):
    def test_unset_entry_is_silent(self):
        self.assertEqual(doc.check_entry_wiring({}, "sa-router", {}, ""), [])
        self.assertEqual(
            doc.check_entry_wiring({"platform": ""}, "sa-router", {}, ""), [])

    def test_route_satisfies(self):
        cfg = {"gateway": {"profile_routes": [
            {"platform": "feishu", "profile": "sa-router"}]}}
        out = doc.check_entry_wiring({"platform": "feishu"}, "sa-router", cfg, "")
        self.assertEqual(out[0]["level"], "ok")

    def test_dedicated_app_satisfies(self):
        out = doc.check_entry_wiring(
            {"platform": "feishu"}, "sa-router", {}, "FEISHU_APP_ID=cli_x\n")
        self.assertEqual(out[0]["level"], "ok")

    def test_unwired_entry_is_an_error_with_the_snippet(self):
        out = doc.check_entry_wiring(
            {"platform": "feishu", "user_id": "ou_1"}, "sa-router", {}, "")
        self.assertEqual(out[0]["level"], "error")
        self.assertIn("profile: sa-router", out[0]["fix"])
        self.assertIn("user_id: ou_1", out[0]["fix"])
