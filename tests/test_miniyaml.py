import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))

import yaml  # noqa: E402

from superagent import miniyaml  # noqa: E402
from superagent.upgrade import pick_python  # noqa: E402

REPO = os.path.join(os.path.dirname(__file__), "..")

FILLED = """
version: 1
providers:
  main:
    type: openai-compatible
    base_url: http://100.64.0.1:3001/v1
    api_key_env: SUPERAGENT_MAIN_API_KEY
router:
  profile: sa-router
  provider: main
  model: deepseek-v4.1-flash
workers:
  - profile: sa-general
    provider: main
    model: deepseek-v4.1-flash
    skills: []
  - profile: sa-deep
    provider: main
    model: glm-5.3
    skills: [deep-research]
policy:
  default_gate: ask
  unattended:
    mode: observe
  sources:
    allow: []
    ask: []
security:
  allow_private_urls: true
limits:
  max_cards_per_run: 5
  ratio: 1.5
  note: "quoted: value # not a comment"
  empty:
"""


class TestMiniYaml(unittest.TestCase):
    def test_matches_pyyaml_on_filled_config(self):
        self.assertEqual(miniyaml.parse(FILLED), yaml.safe_load(FILLED))

    def test_matches_pyyaml_on_the_shipped_template(self):
        with open(os.path.join(REPO, "config", "superagent.yaml"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(miniyaml.parse(text), yaml.safe_load(text))

    def test_scalars(self):
        parsed = miniyaml.parse("a: 1\nb: true\nc: x y\nd: 'it''s'\n")
        self.assertEqual(parsed, {"a": 1, "b": True, "c": "x y", "d": "it's"})

    def test_unsupported_indentation_raises(self):
        with self.assertRaises(ValueError):
            miniyaml.parse("a:\n   b: 1\n  c: 2\n")


class TestYamlLoadFallback(unittest.TestCase):
    def test_fallback_when_pyyaml_missing(self):
        import superagent

        real = sys.modules.get("yaml")

        class Blocker:
            def find_module(self, name, path=None):
                if name == "yaml":
                    return self

            def load_module(self, name):
                raise ImportError("blocked for test")

        blocker = Blocker()
        sys.modules.pop("yaml", None)
        sys.meta_path.insert(0, blocker)
        try:
            out = superagent._yaml_load("a: 1\nb:\n  c: x\n")
        finally:
            sys.meta_path.remove(blocker)
            if real is not None:
                sys.modules["yaml"] = real
        self.assertEqual(out, {"a": 1, "b": {"c": "x"}})


class TestPickPython(unittest.TestCase):
    def test_first_yaml_capable_candidate_wins(self):
        picked = pick_python(probe=lambda exe: exe.endswith("python3") and "bin" in exe)
        self.assertTrue(picked)

    def test_falls_back_to_sys_executable(self):
        self.assertEqual(pick_python(probe=lambda exe: False), sys.executable)


if __name__ == "__main__":
    unittest.main()
