"""The selection surface: `hermes superagent providers` menu data
and doctor's per-role key variables, both read from the default
Hermes config — the suite declares no providers of its own."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugin"))
import superagent as sa  # noqa: E402

DEFAULT_CFG = {
    "model": {"provider": "custom", "default": "m1", "api_key_env": "MAIN_KEY"},
    "providers": {"big": {"name": "big", "base_url": "https://big.example/v1",
                          "key_env": "BIG_KEY"}},
    "custom_providers": [{"name": "lab", "base_url": "http://127.0.0.1:9/v1",
                          "key_env": "LAB_KEY"}],
}


class TestMenu(unittest.TestCase):
    def test_menu_lists_default_and_named(self):
        menu = sa.hermes_provider_menu(DEFAULT_CFG)
        selects = [m["select"] for m in menu]
        self.assertEqual(selects, ["custom", "big", "lab"])
        self.assertTrue(menu[0]["default"])

    def test_empty_config_empty_menu(self):
        self.assertEqual(sa.hermes_provider_menu({}), [])


class TestRoleKeyVars(unittest.TestCase):
    def test_vars_follow_selections(self):
        cfg = {
            "router": {"profile": "sa-router", "provider": "", "model": ""},
            "workers": [
                {"profile": "sa-worker-general", "provider": "lab", "model": ""},
                {"profile": "sa-worker-deep", "provider": "big", "model": "x"},
            ],
        }
        out = sa.resolved_role_key_vars(cfg, DEFAULT_CFG)
        self.assertEqual(out, {
            "sa-router": "MAIN_KEY",
            "sa-worker-general": "LAB_KEY",
            "sa-worker-deep": "BIG_KEY",
        })

    def test_legacy_provider_var_wins(self):
        cfg = {
            "providers": {"main": {"api_key_env": "SUITE_KEY"}},
            "router": {"profile": "sa-router", "provider": "main", "model": "m"},
            "workers": [],
        }
        out = sa.resolved_role_key_vars(cfg, DEFAULT_CFG)
        self.assertEqual(out["sa-router"], "SUITE_KEY")


if __name__ == "__main__":
    unittest.main()
