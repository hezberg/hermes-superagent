import os
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import superagent as sa
from superagent import wizard

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class ScriptedPrompter(wizard.Prompter):
    def __init__(self, answers, secret=""):
        self.answers = list(answers)
        self._secret = secret
        self.output = []
        super().__init__(input_fn=self._next, getpass_fn=lambda p: secret,
                         out=self.output.append)

    def _next(self, prompt=""):
        if not self.answers:
            raise AssertionError(f"wizard asked an unscripted question: {prompt}")
        return self.answers.pop(0)


class TestPureChecks(unittest.TestCase):
    def test_unconfigured_default_profile(self):
        kind, _ = wizard.default_profile_problem({}, "", {})
        self.assertEqual(kind, "unconfigured")

    def test_key_missing_is_a_stop(self):
        cfg = {"model": {"provider": "custom", "default": "m",
                         "api_key_env": "MY_KEY"}}
        kind, var = wizard.default_profile_problem(cfg, "", {})
        self.assertEqual((kind, var), ("key-missing", "MY_KEY"))
        self.assertIsNone(wizard.default_profile_problem(cfg, "MY_KEY=x\n", {}))
        self.assertIsNone(wizard.default_profile_problem(cfg, "", {"MY_KEY": "x"}))
        kind, _ = wizard.default_profile_problem(cfg, "MY_KEY=\n", {})
        self.assertEqual(kind, "key-missing")  # empty value is missing

    def test_app_id_conflicts(self):
        with tempfile.TemporaryDirectory() as home:
            profs = os.path.join(home, "profiles")
            os.makedirs(os.path.join(profs, "other"))
            os.makedirs(os.path.join(profs, "sa-router"))
            with open(os.path.join(profs, "other", ".env"), "w") as fh:
                fh.write("FEISHU_APP_ID=cli_dup\n")
            with open(os.path.join(home, ".env"), "w") as fh:
                fh.write("SOMETHING=1\n")
            hits = wizard.find_app_id_conflicts(home, "cli_dup",
                                                exclude_profile="sa-router")
            self.assertEqual(hits, ["profile other"])
            self.assertEqual(wizard.find_app_id_conflicts(home, "cli_new"), [])

    def test_workers_section_and_entry_edit(self):
        text = open(os.path.join(REPO, "config", "superagent.yaml")).read()
        out = wizard._replace_section(text, "workers",
                                      wizard.workers_section(["general"]))
        cfg = sa._yaml_load(out)
        self.assertEqual([w["name"] for w in cfg["workers"]], ["general"])
        out2 = wizard.set_entry_section(out, "feishu", user_id="ou_1")
        cfg2 = sa._yaml_load(out2)
        self.assertEqual(cfg2["entry"]["platform"], "feishu")
        self.assertEqual(cfg2["entry"]["user_id"], "ou_1")
        # the rest of the file survived the surgery
        self.assertIn("policy", cfg2)
        self.assertIn("watchdog", cfg2)


class WizardCase(unittest.TestCase):
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
        with open(os.path.join(self.home, "config.yaml"), "w") as fh:
            fh.write("model:\n  provider: custom\n  default: base-model\n"
                     "  base_url: http://100.64.0.1:3001/v1\n"
                     "  api_key_env: SUPERAGENT_MAIN_API_KEY\n")
        with open(os.path.join(self.home, ".env"), "w") as fh:
            fh.write("SUPERAGENT_MAIN_API_KEY=sk-test\n")
        self.old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = self.bindir + os.pathsep + self.old_path
        self.calls = []
        self._real_doctor = sa._doctor_findings
        sa._doctor_findings = lambda: []

    def tearDown(self):
        os.environ["PATH"] = self.old_path
        sa._doctor_findings = self._real_doctor
        self.tmp.cleanup()

    def runner(self, argv, env=None, interactive=False):
        self.calls.append(list(argv))
        if "--version" in argv:
            return 0, "Hermes 9.9.9"
        if any("install.py" in a for a in argv):
            full_env = dict(os.environ)
            full_env.update(env or {})
            proc = subprocess.run(argv, env=full_env,
                                  capture_output=True, text=True)
            return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        if "cron" in argv and "list" in argv:
            return 0, "9551201420f8  superagent-reminder-tick.py  every 10m\n"
        return 0, ""

    def run_wizard(self, answers, secret=""):
        ui = ScriptedPrompter(answers, secret=secret)
        rc = wizard.run_wizard(self.home, REPO, prompter=ui,
                               runner=self.runner, environ={})
        return rc, ui


class TestWizardFlow(WizardCase):
    def test_full_run_with_feishu_paste(self):
        rc, ui = self.run_wizard(
            ["1", "1", "1", "2", "cli_newapp123", ""], secret="app-secret")
        self.assertEqual(rc, 0, "\n".join(ui.output))
        cfg = sa._yaml_load(open(os.path.join(
            self.home, "superagent", "superagent.yaml")).read())
        self.assertEqual([w["name"] for w in cfg["workers"]], ["general"])
        self.assertEqual(cfg["entry"]["platform"], "feishu")
        router_env = open(os.path.join(
            self.home, "profiles", "sa-router", ".env")).read()
        self.assertIn("FEISHU_APP_ID=cli_newapp123", router_env)
        self.assertIn("FEISHU_APP_SECRET=app-secret", router_env)
        # delivery was set on the existing tick job
        self.assertTrue(any("9551201420f8" in call and "--deliver" in call
                            for call in self.calls))
        self.assertTrue(any("You are set" in line for line in ui.output))

    def test_duplicate_app_id_is_a_hard_stop_then_recovers(self):
        other = os.path.join(self.home, "profiles", "other")
        os.makedirs(other)
        with open(os.path.join(other, ".env"), "w") as fh:
            fh.write("FEISHU_APP_ID=cli_dup\n")
        rc, ui = self.run_wizard(
            ["1", "1", "1", "2", "cli_dup", "", "cli_fresh", ""],
            secret="s3cret")
        self.assertEqual(rc, 0, "\n".join(ui.output))
        self.assertTrue(any("already used by" in line for line in ui.output))
        router_env = open(os.path.join(
            self.home, "profiles", "sa-router", ".env")).read()
        self.assertIn("FEISHU_APP_ID=cli_fresh", router_env)

    def test_unconfigured_hermes_exits_before_any_question(self):
        os.remove(os.path.join(self.home, "config.yaml"))
        ui = ScriptedPrompter([])
        rc = wizard.run_wizard(self.home, REPO, prompter=ui,
                               runner=self.runner, environ={})
        self.assertEqual(rc, 2)
        self.assertTrue(any("hermes setup" in line for line in ui.output))
        self.assertFalse(any("install.py" in a
                             for call in self.calls for a in call))
