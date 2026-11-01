import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import inherit  # noqa: E402
import miniyaml  # noqa: E402

BLOCK = {
    "provider": "custom",
    "default": "cn:deepseek-v4.1-flash",
    "base_url": "http://100.64.0.1:3001/v1",
    "api_key_env": "SUPERAGENT_MAIN_API_KEY",
}

CFG = {
    "version": 1,
    "providers": {"main": {"type": "openai-compatible", "base_url": "",
                           "api_key_env": "SUPERAGENT_MAIN_API_KEY"}},
    "router": {"profile": "sa-router", "provider": "main", "model": ""},
    "workers": [
        {"name": "general", "profile": "sa-worker-general", "provider": "main",
         "model": ""},
        {"name": "deep", "profile": "sa-worker-deep", "provider": "main",
         "model": "glm-5.3"},
    ],
}


class TestApplyInheritance(unittest.TestCase):
    def test_model_less_roles_inherit_explicit_ones_do_not(self):
        eff, inherited = inherit.apply_inheritance(CFG, BLOCK)
        self.assertEqual(inherited, ["sa-router", "sa-worker-general"])
        router = eff["router"]
        self.assertEqual(router["provider"], inherit.INHERITED)
        self.assertEqual(router["model"], "cn:deepseek-v4.1-flash")
        deep = eff["workers"][1]
        self.assertEqual(deep["model"], "glm-5.3")
        self.assertEqual(deep["provider"], "main")
        verbatim = eff["providers"][inherit.INHERITED]
        self.assertEqual(verbatim["type"], "__verbatim__")
        self.assertEqual(verbatim["api_key_env"], "SUPERAGENT_MAIN_API_KEY")
        # The operator's own dict is not mutated.
        self.assertEqual(CFG["router"]["model"], "")

    def test_key_env_alias_is_accepted(self):
        block = {"provider": "custom", "default": "m", "key_env": "MY_KEY"}
        eff, _ = inherit.apply_inheritance(CFG, block)
        self.assertEqual(
            eff["providers"][inherit.INHERITED]["api_key_env"], "MY_KEY")

    def test_no_model_in_block_means_no_inheritance(self):
        eff, inherited = inherit.apply_inheritance(CFG, {"provider": "custom"})
        self.assertEqual(inherited, [])
        self.assertNotIn(inherit.INHERITED, eff.get("providers") or {})

    def test_model_key_fallback(self):
        block = {"provider": "custom", "model": "legacy-name"}
        _eff, inherited = inherit.apply_inheritance(CFG, block)
        self.assertEqual(len(inherited), 2)


class TestDump(unittest.TestCase):
    def test_effective_config_roundtrips(self):
        eff, _ = inherit.apply_inheritance(CFG, BLOCK)
        text = inherit.dump_simple_yaml(eff)
        self.assertEqual(miniyaml.parse(text), eff)


if __name__ == "__main__":
    unittest.main()


DEFAULT_CFG = {
    "model": {
        "provider": "custom:lab",
        "default": "lab-default-model",
        "api_key_env": "LAB_KEY",
    },
    "providers": {
        "big": {"name": "big", "base_url": "https://big.example/v1",
                "key_env": "BIG_KEY", "model": "big-1"},
    },
    "custom_providers": [
        {"name": "lab", "base_url": "http://127.0.0.1:3001/v1",
         "key_env": "LAB_KEY"},
        {"name": "glm", "base_url": "https://glm.example/v1",
         "api_key_env": "GLM_KEY", "default": "glm-5.3"},
    ],
}

SEL_CFG = {
    "version": 1,
    "router": {"profile": "sa-router", "provider": "", "model": ""},
    "workers": [
        {"name": "general", "profile": "sa-worker-general", "provider": "glm",
         "model": ""},
        {"name": "deep", "profile": "sa-worker-deep", "provider": "big",
         "model": "big-2"},
    ],
}


class TestResolution(unittest.TestCase):
    def test_empty_selection_inherits_and_carries_the_referenced_entry(self):
        eff, notes, errors = inherit.apply_resolution(SEL_CFG, DEFAULT_CFG)
        self.assertEqual(errors, [])
        router = eff["router"]
        self.assertEqual(router["provider"], inherit.INHERITED)
        verbatim = eff["providers"][inherit.INHERITED]
        # the default block points at custom:lab, so the lab entry
        # must travel into the rendered profile (Hermes seeding rule)
        self.assertEqual(verbatim["sections"]["custom_providers"][0]["name"], "lab")

    def test_named_entry_selection(self):
        eff, _notes, errors = inherit.apply_resolution(SEL_CFG, DEFAULT_CFG)
        self.assertEqual(errors, [])
        general = eff["workers"][0]
        entry = eff["providers"][general["provider"]]
        self.assertEqual(entry["model_block"]["provider"], "custom:glm")
        self.assertEqual(entry["model_block"]["default"], "glm-5.3")
        self.assertEqual(entry["api_key_env"], "GLM_KEY")
        self.assertEqual(entry["sections"]["custom_providers"][0]["name"], "glm")

    def test_providers_dict_selection_by_key_with_model_override(self):
        eff, _notes, errors = inherit.apply_resolution(SEL_CFG, DEFAULT_CFG)
        self.assertEqual(errors, [])
        deep = eff["workers"][1]
        entry = eff["providers"][deep["provider"]]
        self.assertEqual(entry["model_block"]["provider"], "custom:big")
        self.assertEqual(entry["model_block"]["default"], "big-2")
        self.assertIn("big", entry["sections"]["providers"])
        self.assertEqual(entry["api_key_env"], "BIG_KEY")

    def test_model_only_override_keeps_default_provider(self):
        cfg = {"version": 1,
               "router": {"profile": "sa-router", "provider": "", "model": "other"},
               "workers": []}
        eff, _notes, errors = inherit.apply_resolution(cfg, DEFAULT_CFG)
        self.assertEqual(errors, [])
        entry = eff["providers"][eff["router"]["provider"]]
        self.assertEqual(entry["model_block"]["provider"], "custom:lab")
        self.assertEqual(entry["model_block"]["default"], "other")

    def test_unknown_provider_is_an_error_with_the_menu(self):
        cfg = {"version": 1,
               "router": {"profile": "sa-router", "provider": "nope", "model": "x"},
               "workers": []}
        _eff, _notes, errors = inherit.apply_resolution(cfg, DEFAULT_CFG)
        self.assertEqual(len(errors), 1)
        self.assertIn("custom:glm", errors[0])
        self.assertIn("Available selections", errors[0])

    def test_registry_lists_both_sources(self):
        entries = inherit.provider_registry(DEFAULT_CFG)
        refs = sorted(e["ref"] for e in entries)
        self.assertEqual(refs, ["custom:big", "custom:glm", "custom:lab"])
