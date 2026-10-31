import importlib.util
import os
import sys
import tempfile
import unittest

import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load_module(name, relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


render = load_module("render_profiles", "scripts/render_profiles.py")
validate_mod = load_module("validate_config", "scripts/validate_config.py")


class TestRenderDeepseekExample(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "config/examples/deepseek.yaml"),
                  encoding="utf-8") as fh:
            self.cfg = yaml.safe_load(fh)
        self.tmp = tempfile.TemporaryDirectory()
        self.written = render.render_all(
            self.cfg, os.path.join(ROOT, "profiles"), self.tmp.name
        )

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, profile):
        with open(os.path.join(self.tmp.name, profile, "config.yaml"),
                  encoding="utf-8") as fh:
            return fh.read()

    def test_all_profiles_rendered(self):
        names = sorted(os.path.basename(p) for p in self.written)
        self.assertEqual(
            names,
            ["sa-router", "sa-worker-deep", "sa-worker-general", "sa-worker-research"],
        )

    def test_router_gets_deepseek_chat_and_no_placeholders(self):
        text = self.read("sa-router")
        self.assertIn("deepseek-chat", text)
        self.assertIn("https://api.deepseek.com", text)
        self.assertNotIn("{{", text)
        # Router selection is exactly kanban + memory + skills, via
        # platform_toolsets (agent.toolsets is not read by Hermes).
        self.assertIn("platform_toolsets", text)
        self.assertIn("cli: [kanban, memory, skills]", text)
        self.assertNotIn("agent:", text)

    def test_worker_toolsets_gain_memory_and_skills(self):
        text = self.read("sa-worker-general")
        self.assertIn("platform_toolsets", text)
        self.assertIn("cli: [terminal, file, web, memory, skills]", text)

    def test_deep_worker_gets_reasoner(self):
        self.assertIn("deepseek-reasoner", self.read("sa-worker-deep"))

    def test_example_config_validates_clean(self):
        errors, warnings = validate_mod.validate(self.cfg)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


class TestRenderAnthropic(unittest.TestCase):
    def test_anthropic_provider_maps_through(self):
        cfg = {
            "version": 1,
            "providers": {
                "alt": {"type": "anthropic",
                        "base_url": "https://api.anthropic.com",
                        "api_key_env": "ALT_KEY"}
            },
            "router": {"profile": "sa-router", "provider": "alt",
                       "model": "claude-example"},
            "workers": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            render.render_all(cfg, os.path.join(ROOT, "profiles"), tmp)
            with open(os.path.join(tmp, "sa-router", "config.yaml"),
                      encoding="utf-8") as fh:
                text = fh.read()
        self.assertIn("anthropic", text)
        self.assertIn("claude-example", text)
        self.assertNotIn("{{", text)


class TestTemplateWarnings(unittest.TestCase):
    def test_shipped_template_has_warnings_not_errors(self):
        with open(os.path.join(ROOT, "config/superagent.yaml"),
                  encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        errors, warnings = validate_mod.validate(cfg)
        self.assertEqual(errors, [])
        self.assertTrue(warnings)  # empty model/base_url must warn


if __name__ == "__main__":
    unittest.main()
