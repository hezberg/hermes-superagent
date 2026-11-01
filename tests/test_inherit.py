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
