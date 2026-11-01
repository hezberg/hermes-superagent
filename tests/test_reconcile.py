"""Config edits apply themselves: staleness detection, reconcile
bookkeeping (fail once per config version, retry when a human is
watching), and the comment-preserving set-model text edit."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugin"))
from superagent import reconcile  # noqa: E402


class SuiteCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sa-reconcile-")
        self.home = os.path.join(self.tmp, "home")
        self.suite = os.path.join(self.home, "superagent")
        self.src = os.path.join(self.suite, "src")
        os.makedirs(os.path.join(self.src, "scripts"))
        with open(os.path.join(self.suite, "state.json"), "w") as fh:
            json.dump({"schema": 1}, fh)
        self.cfg = os.path.join(self.suite, "superagent.yaml")
        with open(self.cfg, "w") as fh:
            fh.write("router:\n  profile: sa-router\n")
        old = time.time() - 100
        os.utime(self.cfg, (old, old))  # installed-after-edit: fresh

    def run_reconcile(self, code=0, output="", interactive=False):
        calls = []

        def runner(cmd):
            calls.append(cmd)
            return code, output

        with open(os.path.join(self.src, "scripts", "install.py"), "w") as fh:
            fh.write("# stub\n")
        result = reconcile.maybe_reconcile(self.home, self.suite,
                                           interactive=interactive, runner=runner)
        return result, calls

    def make_stale(self):
        future = time.time() + 5
        os.utime(self.cfg, (future, future))


class TestMaybeReconcile(SuiteCase):
    def test_fresh_config_is_a_no_op(self):
        result, calls = self.run_reconcile()
        self.assertEqual(result["status"], "fresh")
        self.assertEqual(calls, [])

    def test_stale_config_reconciles_via_the_installer(self):
        self.make_stale()
        result, calls = self.run_reconcile(code=0)
        self.assertEqual(result["status"], "reconciled")
        self.assertEqual(len(calls), 1)
        self.assertIn("install.py", calls[0][1])

    def test_failure_is_reported_once_per_config_version(self):
        self.make_stale()
        first, calls1 = self.run_reconcile(code=1, output="ERROR: bad config\n")
        self.assertEqual(first["status"], "failed")
        self.assertIn("bad config", first["message"])
        second, calls2 = self.run_reconcile(code=1, output="ERROR: bad config\n")
        self.assertEqual(second["status"], "failed")
        self.assertIsNone(second["message"])   # the tick stays quiet now
        self.assertEqual(calls2, [])           # and does not retry blindly

    def test_interactive_call_retries_a_failed_version(self):
        self.make_stale()
        self.run_reconcile(code=1, output="ERROR: bad config\n")
        retry, calls = self.run_reconcile(code=0, interactive=True)
        self.assertEqual(retry["status"], "reconciled")
        self.assertEqual(len(calls), 1)

    def test_missing_source_is_skipped_not_failed(self):
        self.make_stale()
        result = reconcile.maybe_reconcile(
            self.home, self.suite, runner=lambda cmd: (0, ""))
        self.assertEqual(result["status"], "skipped")


CONFIG_TEXT = """\
# a comment the operator wrote
router:
  profile: sa-router
  provider: main
  model: "old-router-model"

workers:
  - name: general
    profile: sa-worker-general
    provider: main
    model: ""
  - name: deep
    profile: sa-worker-deep
    provider: main
"""


class TestSetRoleModel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sa-setmodel-")
        self.suite = os.path.join(self.tmp, "superagent")
        os.makedirs(self.suite)
        self.path = os.path.join(self.suite, "superagent.yaml")
        with open(self.path, "w") as fh:
            fh.write(CONFIG_TEXT)

    def read(self):
        with open(self.path) as fh:
            return fh.read()

    def test_replaces_an_existing_model_line(self):
        self.assertTrue(reconcile.set_role_model(self.suite, "sa-router", "new-model"))
        text = self.read()
        self.assertIn('model: "new-model"', text)
        self.assertIn("# a comment the operator wrote", text)

    def test_does_not_touch_other_roles(self):
        reconcile.set_role_model(self.suite, "sa-worker-general", "g-model")
        text = self.read()
        self.assertIn('model: "old-router-model"', text)
        lines = text.split("\n")
        idx = next(i for i, ln in enumerate(lines) if "sa-worker-general" in ln)
        self.assertIn('model: "g-model"', lines[idx + 2])

    def test_inserts_when_the_role_has_no_model_line(self):
        self.assertTrue(reconcile.set_role_model(self.suite, "sa-worker-deep", "deep-x"))
        text = self.read()
        self.assertIn('model: "deep-x"', text)
        # inserted inside the deep block, after its profile line
        idx = text.index("sa-worker-deep")
        self.assertGreater(text.index('model: "deep-x"'), idx)

    def test_unknown_profile_returns_false_and_writes_nothing(self):
        self.assertFalse(reconcile.set_role_model(self.suite, "sa-nope", "x"))
        self.assertEqual(self.read(), CONFIG_TEXT)

    def test_empty_model_means_inherit(self):
        self.assertTrue(reconcile.set_role_model(self.suite, "sa-router", ""))
        self.assertIn('model: ""', self.read())


class TestTickReconciles(unittest.TestCase):
    def test_tick_prints_a_failed_reconcile_once(self):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(repo, "plugin"))
        import superagent as sa

        with tempfile.TemporaryDirectory() as home:
            suite = os.path.join(home, "superagent")
            src = os.path.join(home, "src")
            os.makedirs(os.path.join(src, "scripts"))
            os.makedirs(os.path.join(home, "plugins"))
            os.makedirs(suite)
            with open(os.path.join(src, "scripts", "install.py"), "w") as fh:
                fh.write("import sys\nprint('ERROR: deliberately broken')\nsys.exit(1)\n")
            with open(os.path.join(suite, "superagent.yaml"), "w") as fh:
                fh.write("{}\n")
            with open(os.path.join(suite, "state.json"), "w") as fh:
                json.dump({"source_repo": src}, fh)
            cfg = os.path.join(suite, "superagent.yaml")
            future = time.time() + 60
            os.utime(cfg, (future, future))
            env = dict(os.environ, HERMES_HOME=home, HOME=home)
            with open(os.path.join(repo, "scripts", "reminder_tick.py")) as fh:
                body = fh.read().replace("__HERMES_HOME__", home)
            tick_path = os.path.join(home, "tick.py")
            with open(tick_path, "w") as fh:
                fh.write(body)
            # the plugin package must be importable by the tick
            link = os.path.join(home, "plugins", "superagent")
            os.symlink(os.path.join(repo, "plugin", "superagent"), link)
            first = subprocess.run([sys.executable, tick_path], env=env,
                                   capture_output=True, text=True)
            self.assertIn("NOT applied", first.stdout)
            second = subprocess.run([sys.executable, tick_path], env=env,
                                    capture_output=True, text=True)
            self.assertNotIn("NOT applied", second.stdout)


if __name__ == "__main__":
    unittest.main()
