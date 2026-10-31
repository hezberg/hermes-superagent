import importlib.util
import os
import tempfile
import unittest

import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load_module(name, relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pick = load_module("pick_config", "scripts/pick_config.py")

PRISTINE = {
    "version": 1,
    "providers": {"main": {"type": "openai-compatible", "base_url": "",
                           "api_key_env": "K"}},
    "router": {"profile": "sa-router", "provider": "main", "model": ""},
    "workers": [],
}
FILLED = {
    "version": 1,
    "providers": {"main": {"type": "openai-compatible",
                           "base_url": "http://100.64.0.1:3001/v1",
                           "api_key_env": "K"}},
    "router": {"profile": "sa-router", "provider": "main",
               "model": "deepseek-v4.1-flash"},
    "workers": [],
}


class TestPickConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo.yaml")
        self.suite = os.path.join(self.tmp.name, "suite.yaml")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, cfg):
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(cfg, fh)

    def test_pristine_detection(self):
        self.assertTrue(pick.is_pristine(PRISTINE))
        self.assertFalse(pick.is_pristine(FILLED))
        self.assertTrue(pick.is_pristine(None))
        self.assertTrue(pick.is_pristine({}))

    def test_filled_suite_wins_over_pristine_repo(self):
        self.write(self.repo, PRISTINE)
        self.write(self.suite, FILLED)
        chosen, from_suite = pick.choose(self.repo, self.suite)
        self.assertEqual(chosen, self.suite)
        self.assertTrue(from_suite)

    def test_filled_repo_wins(self):
        self.write(self.repo, FILLED)
        self.write(self.suite, FILLED)
        chosen, from_suite = pick.choose(self.repo, self.suite)
        self.assertEqual(chosen, self.repo)
        self.assertFalse(from_suite)

    def test_missing_suite_falls_back_to_repo(self):
        self.write(self.repo, PRISTINE)
        chosen, from_suite = pick.choose(self.repo, self.suite)
        self.assertEqual(chosen, self.repo)
        self.assertFalse(from_suite)


if __name__ == "__main__":
    unittest.main()
