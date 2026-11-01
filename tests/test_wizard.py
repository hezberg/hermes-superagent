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
            fh.write("SUPERAGENT_MAIN_API_KEY=sk-test\nWB_KEY=sk-wb\n")
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

    def run_wizard(self, answers, secret="", fetcher=None):
        ui = ScriptedPrompter(answers, secret=secret)
        rc = wizard.run_wizard(
            self.home, REPO, prompter=ui, runner=self.runner, environ={},
            fetcher=fetcher if fetcher is not None else (lambda url, key: None))
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


class TestWizardNamedProvider(WizardCase):
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.home, "config.yaml"), "w") as fh:
            fh.write(
                "model:\n  provider: custom\n  default: base-model\n"
                "  base_url: http://100.64.0.1:3001/v1\n"
                "  api_key_env: SUPERAGENT_MAIN_API_KEY\n"
                "custom_providers:\n"
                "  - name: workbuddy\n"
                "    base_url: http://100.64.0.1:3001/v1\n"
                "    model: cn:deepseek-v4.1-flash\n"
                "    api_key_env: WB_KEY\n")

    def test_named_provider_model_prefilled_but_editable(self):
        # topology=1, router picks workbuddy (2); the model prompt
        # follows with the entry's model as default: "" keeps it.
        # worker inherits, no chat entry.
        rc, ui = self.run_wizard(["1", "2", "", "1", "1"])
        self.assertEqual(rc, 0, "\n".join(ui.output))
        cfg = sa._yaml_load(open(os.path.join(
            self.home, "superagent", "superagent.yaml")).read())
        self.assertEqual(cfg["router"]["provider"], "workbuddy")
        self.assertEqual(cfg["router"]["model"], "cn:deepseek-v4.1-flash")
        self.assertEqual(ui.answers, [])  # every answer consumed as scripted

    def test_named_provider_other_model_wins(self):
        # Same menu, but the operator types a DIFFERENT model than
        # the provider entry's own — that choice must be honored.
        rc, ui = self.run_wizard(["1", "2", "cn:another-model", "1", "1"])
        self.assertEqual(rc, 0, "\n".join(ui.output))
        cfg = sa._yaml_load(open(os.path.join(
            self.home, "superagent", "superagent.yaml")).read())
        self.assertEqual(cfg["router"]["provider"], "workbuddy")
        self.assertEqual(cfg["router"]["model"], "cn:another-model")


class TestStyle(unittest.TestCase):
    def make(self, enabled):
        lines = []
        return wizard.Prompter(input_fn=lambda p="": "1",
                               out=lines.append,
                               style=wizard.Style(enabled=enabled)), lines

    def test_color_on_marks_errors_and_defaults(self):
        ui, lines = self.make(True)
        ui.error("STOP: something")
        ui.choose("Pick", ["alpha", "beta"], default=1)
        blob = "\n".join(lines)
        self.assertIn("\033[1;31m", blob)
        self.assertIn("✗ STOP:", blob)
        self.assertIn("← default", blob)

    def test_color_off_is_plain(self):
        ui, lines = self.make(False)
        ui.error("STOP: something")
        ui.ok("done")
        blob = "\n".join(lines)
        self.assertNotIn("\033[", blob)
        self.assertIn("✗ STOP:", blob)


class TestBindPathDuplicates(WizardCase):
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.home, ".env"), "a") as fh:
            fh.write("FEISHU_APP_ID=cli_dupapp\n")
        self.setup_ids = ["cli_dupapp", "cli_freshapp"]

    def runner(self, argv, env=None, interactive=False):
        if "gateway" in argv and "setup" in argv:
            app_id = self.setup_ids.pop(0)
            router_env = os.path.join(
                self.home, "profiles", "sa-router", ".env")
            os.makedirs(os.path.dirname(router_env), exist_ok=True)
            with open(router_env, "a") as fh:
                fh.write(f"FEISHU_APP_ID={app_id}\nFEISHU_APP_SECRET=x\n")
            return 0, ""
        return super().runner(argv, env=env, interactive=interactive)

    def test_duplicate_bind_is_a_stop_and_rebind_recovers(self):
        # feishu via Hermes setup (3), then confirm remove+rebind (""
        # = default yes), then accept the gateway restart ("").
        rc, ui = self.run_wizard(["1", "1", "1", "3", "", ""])
        self.assertEqual(rc, 0, "\n".join(ui.output))
        self.assertTrue(any("STOP:" in line for line in ui.output))
        router_env = open(os.path.join(
            self.home, "profiles", "sa-router", ".env")).read()
        self.assertIn("FEISHU_APP_ID=cli_freshapp", router_env)
        self.assertNotIn("cli_dupapp", router_env)
        cfg = sa._yaml_load(open(os.path.join(
            self.home, "superagent", "superagent.yaml")).read())
        self.assertEqual(cfg["entry"]["platform"], "feishu")

    def test_duplicate_bind_removed_when_rebind_declined(self):
        # decline rebind ("n"), accept removal ("" = default yes)
        rc, ui = self.run_wizard(["1", "1", "1", "3", "n", ""])
        self.assertEqual(rc, 1, "\n".join(ui.output))
        self.assertTrue(any("NOT configured" in line for line in ui.output))
        router_env_path = os.path.join(
            self.home, "profiles", "sa-router", ".env")
        router_env = open(router_env_path).read()
        self.assertNotIn("FEISHU_APP_ID", router_env)
        cfg = sa._yaml_load(open(os.path.join(
            self.home, "superagent", "superagent.yaml")).read())
        self.assertEqual(cfg["entry"]["platform"], "")


class TestModelListFromProvider(WizardCase):
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.home, "config.yaml"), "w") as fh:
            fh.write(
                "model:\n  provider: custom\n  default: base-model\n"
                "  base_url: http://100.64.0.1:3001/v1\n"
                "  api_key_env: SUPERAGENT_MAIN_API_KEY\n"
                "custom_providers:\n"
                "  - name: workbuddy\n"
                "    base_url: http://100.64.0.1:3001/v1\n"
                "    model: cn:deepseek-v4.1-flash\n"
                "    api_key_env: WB_KEY\n")

    def fetcher(self, url, key):
        self.assertEqual(url, "http://100.64.0.1:3001/v1")
        return ["glm-5.3", "cn:deepseek-v4.1-flash", "deepseek-v4.1-pro"]

    def test_pick_from_fetched_list(self):
        # router: provider workbuddy (2), model list pick 1 (glm-5.3);
        # worker inherits; no entry.
        rc, ui = self.run_wizard(["1", "2", "1", "1", "1"],
                                 fetcher=self.fetcher)
        self.assertEqual(rc, 0, "\n".join(ui.output))
        cfg = sa._yaml_load(open(os.path.join(
            self.home, "superagent", "superagent.yaml")).read())
        self.assertEqual(cfg["router"]["provider"], "workbuddy")
        self.assertEqual(cfg["router"]["model"], "glm-5.3")
        self.assertEqual(ui.answers, [])


class TestTransactionalWizard(WizardCase):
    def test_interrupt_at_secret_entry_changes_nothing(self):
        def boom(prompt=""):
            raise KeyboardInterrupt
        ui = wizard.Prompter(input_fn=None, getpass_fn=boom,
                             out=lambda m: None, style=wizard.Style(enabled=False))
        answers = iter(["1", "1", "1", "2", "cli_newapp999"])
        ui._input = lambda prompt="": next(answers)
        rc = wizard.run_wizard(self.home, REPO, prompter=ui,
                               runner=self.runner, environ={},
                               fetcher=lambda url, key: None)
        self.assertEqual(rc, 130)
        self.assertFalse(os.path.exists(os.path.join(
            self.home, "profiles", "sa-router", ".env")))
        self.assertFalse(os.path.exists(os.path.join(
            self.home, "superagent", "superagent.yaml")))

    def test_interrupt_restores_bind_path_env(self):
        router_env = os.path.join(self.home, "profiles", "sa-router", ".env")
        os.makedirs(os.path.dirname(router_env))
        with open(router_env, "w") as fh:
            fh.write("PREEXISTING=1\n")

        def runner(argv, env=None, interactive=False):
            if "gateway" in argv and "setup" in argv:
                with open(router_env, "a") as fh:
                    fh.write("FEISHU_APP_ID=cli_bound\n")
                raise KeyboardInterrupt  # user bails mid-setup return
            return self.runner(argv, env=env, interactive=interactive)

        ui = ScriptedPrompter(["1", "1", "1", "3"])
        rc = wizard.run_wizard(self.home, REPO, prompter=ui,
                               runner=runner, environ={},
                               fetcher=lambda url, key: None)
        self.assertEqual(rc, 130)
        with open(router_env) as fh:
            self.assertEqual(fh.read(), "PREEXISTING=1\n")


class TestBindNothingBound(WizardCase):
    """Hermes' inner setup can end with nothing bound (another
    platform chosen, or the step skipped). Step 4 must fail loudly
    and loop back, not carry on entry-less."""

    def setUp(self):
        super().setUp()
        self.setup_calls = 0

    def runner(self, argv, env=None, interactive=False):
        if "gateway" in argv and "setup" in argv:
            self.setup_calls += 1
            if self.setup_calls >= 2:  # second attempt binds properly
                router_env = os.path.join(
                    self.home, "profiles", "sa-router", ".env")
                os.makedirs(os.path.dirname(router_env), exist_ok=True)
                with open(router_env, "a") as fh:
                    fh.write("FEISHU_APP_ID=cli_second_try\nFEISHU_APP_SECRET=x\n")
            return 0, ""
        return super().runner(argv, env=env, interactive=interactive)

    def test_nothing_bound_loops_back_and_recovers(self):
        # feishu via setup (3); recovery menu: retry (1); restart yes ("")
        rc, ui = self.run_wizard(["1", "1", "1", "3", "1", ""])
        self.assertEqual(rc, 0, "\n".join(ui.output))
        self.assertEqual(self.setup_calls, 2)
        self.assertTrue(any("NO Feishu app was" in line for line in ui.output))
        cfg = sa._yaml_load(open(os.path.join(
            self.home, "superagent", "superagent.yaml")).read())
        self.assertEqual(cfg["entry"]["platform"], "feishu")

    def test_nothing_bound_then_give_up(self):
        # recovery menu: give up (3) — explicit, recorded as failed
        rc, ui = self.run_wizard(["1", "1", "1", "3", "3"])
        self.assertEqual(rc, 1, "\n".join(ui.output))
        self.assertEqual(self.setup_calls, 1)
        self.assertTrue(any("NOT configured" in line for line in ui.output))
