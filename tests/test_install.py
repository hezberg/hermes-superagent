import json
import os
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")
INSTALL = os.path.join(ROOT, "scripts", "install.py")
UNINSTALL = os.path.join(ROOT, "scripts", "uninstall.py")
VERSION = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()

FILLED = {
    "version": 1,
    "providers": {"main": {"type": "openai-compatible",
                           "base_url": "http://100.64.0.1:3001/v1",
                           "api_key_env": "SUPERAGENT_MAIN_API_KEY"}},
    "router": {"profile": "sa-router", "provider": "main",
               "model": "deepseek-v4.1-flash", "reasoning_effort": ""},
    "workers": [
        {"name": "general", "profile": "sa-worker-general", "role": "general",
         "provider": "main", "model": "deepseek-v4.1-flash",
         "reasoning_effort": "", "toolsets": ["terminal", "file", "web"],
         "max_concurrent": 2},
        {"name": "research", "profile": "sa-worker-research", "role": "research",
         "provider": "main", "model": "deepseek-v4.1-flash",
         "reasoning_effort": "", "toolsets": ["web", "file"],
         "max_concurrent": 1},
    ],
    "policy": {"accept_mode": "observe",
               "sources": {"cli": {"allowed_senders": []},
                           "feishu": {"allowed_senders": []},
                           "webhook": {"allowed_senders": []}},
               "bots": [], "rules": []},
    "watchdog": {"enabled": True, "interval_minutes": 10,
                 "authority": "report-only", "stall_minutes": 30,
                 "heartbeat_stale_minutes": 15},
    "events": {"fastpath": []},
    "limits": {"max_workers": 4, "reserved_human_slot": True,
               "router_reply_max_words": 100},
    "security": {"allow_private_urls": True},
}


class InstallerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        self.bindir = os.path.join(self.tmp.name, "bin")
        os.makedirs(self.home)
        os.makedirs(self.bindir)
        fake = os.path.join(self.bindir, "hermes")
        with open(fake, "w") as fh:
            fh.write("#!/bin/sh\nexit 0\n")
        os.chmod(fake, 0o755)
        with open(os.path.join(self.home, ".env"), "w") as fh:
            fh.write("SUPERAGENT_MAIN_API_KEY=dummy\n")
        self.env = dict(os.environ)
        self.env["PATH"] = self.bindir + os.pathsep + self.env["PATH"]
        self.env["HERMES_HOME"] = self.home

    def tearDown(self):
        self.tmp.cleanup()

    def run_install(self, *extra):
        return subprocess.run(
            [sys.executable, INSTALL, *extra],
            capture_output=True, text=True, env=self.env, timeout=120,
        )

    def run_uninstall(self, *extra):
        return subprocess.run(
            [sys.executable, UNINSTALL, *extra],
            capture_output=True, text=True, env=self.env, timeout=120,
        )

    def suite_cfg_path(self):
        return os.path.join(self.home, "superagent", "superagent.yaml")

    def write_suite_config(self, cfg=None):
        os.makedirs(os.path.dirname(self.suite_cfg_path()), exist_ok=True)
        with open(self.suite_cfg_path(), "w", encoding="utf-8") as fh:
            yaml.safe_dump(cfg or FILLED, fh, allow_unicode=True)

    def install_filled(self):
        self.write_suite_config()
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result


class TestTwoPhase(InstallerCase):
    def test_first_run_generates_config_and_stops(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertTrue(os.path.isfile(self.suite_cfg_path()))
        self.assertFalse(os.path.exists(
            os.path.join(self.home, "plugins", "superagent")))

    def test_pristine_suite_config_stops_too(self):
        template = os.path.join(ROOT, "config", "superagent.yaml")
        os.makedirs(os.path.dirname(self.suite_cfg_path()), exist_ok=True)
        with open(template, encoding="utf-8") as src, \
                open(self.suite_cfg_path(), "w", encoding="utf-8") as dst:
            dst.write(src.read())
        result = self.run_install()
        self.assertEqual(result.returncode, 3, result.stdout)


class TestConverge(InstallerCase):
    def test_seed_via_explicit_config(self):
        staging = os.path.join(self.tmp.name, "staging.yaml")
        with open(staging, "w", encoding="utf-8") as fh:
            yaml.safe_dump(FILLED, fh)
        result = self.run_install("--config", staging)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with open(self.suite_cfg_path(), encoding="utf-8") as fh:
            seeded = yaml.safe_load(fh)
        self.assertEqual(seeded["router"]["model"], "deepseek-v4.1-flash")
        state = json.load(open(os.path.join(
            self.home, "superagent", "state.json"), encoding="utf-8"))
        self.assertEqual(state["version"], VERSION)
        init_py = open(os.path.join(
            self.home, "plugins", "superagent", "__init__.py"),
            encoding="utf-8").read()
        self.assertIn(f'PLUGIN_VERSION = "{VERSION}"', init_py)

    def test_second_run_changes_nothing(self):
        self.install_filled()
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Changed: nothing", result.stdout)

    def test_config_change_rerenders_profiles(self):
        self.install_filled()
        cfg = dict(FILLED)
        cfg["router"] = dict(FILLED["router"], model="glm-5.3")
        self.write_suite_config(cfg)
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout)
        rendered = open(os.path.join(
            self.home, "profiles", "sa-router", "config.yaml"),
            encoding="utf-8").read()
        self.assertIn("glm-5.3", rendered)
        self.assertIn("profile sa-router", result.stdout)

    def test_rollback_restores_previous_generation(self):
        self.install_filled()
        self.run_install()  # second run snapshots generation one
        victim = os.path.join(self.home, "plugins", "superagent", "doctor.py")
        os.remove(victim)
        result = self.run_install("--rollback")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(os.path.isfile(victim))

    def test_legacy_manifest_migrates(self):
        self.write_suite_config()
        legacy = {
            "suite": "hermes-superagent", "version": "0.2.1",
            "installed_at": "2026-10-31T22:00:00+0800",
            "created_paths": [
                os.path.join(self.home, "plugins", "superagent"),
                os.path.join(self.home, "superagent"),
                os.path.join(self.home, "profiles", "sa-router"),
            ],
        }
        with open(os.path.join(self.home, "superagent", "manifest.json"),
                  "w", encoding="utf-8") as fh:
            json.dump(legacy, fh)
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = json.load(open(os.path.join(
            self.home, "superagent", "state.json"), encoding="utf-8"))
        self.assertEqual(state["version"], VERSION)


class TestUninstall(InstallerCase):
    def test_uninstall_keeps_user_data_then_purge(self):
        self.install_filled()
        journal = os.path.join(self.home, "superagent", "journal.md")
        with open(journal, "w") as fh:
            fh.write("history")
        result = self.run_uninstall()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(os.path.exists(
            os.path.join(self.home, "plugins", "superagent")))
        self.assertFalse(os.path.exists(
            os.path.join(self.home, "profiles", "sa-router")))
        self.assertTrue(os.path.isfile(self.suite_cfg_path()))
        self.assertTrue(os.path.isfile(journal))
        # state is gone, so a second uninstall has nothing to go on
        self.assertEqual(self.run_uninstall().returncode, 1)


if __name__ == "__main__":
    unittest.main()
