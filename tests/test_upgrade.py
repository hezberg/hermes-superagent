import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))

from superagent import upgrade as up  # noqa: E402

SUITE = "/home/x/.hermes/superagent"
MANAGED = os.path.join(SUITE, "src")


def fake_is(*valid):
    valid = set(valid)
    return lambda p: p in valid


class TestPickSource(unittest.TestCase):
    def test_recorded_checkout_wins(self):
        state = {"source_repo": "/work/checkout"}
        mode, path = up.pick_source(state, SUITE, fake_is("/work/checkout", MANAGED))
        self.assertEqual((mode, path), ("recorded", "/work/checkout"))

    def test_recorded_gone_falls_back_to_managed(self):
        state = {"source_repo": "/gone"}
        mode, path = up.pick_source(state, SUITE, fake_is(MANAGED))
        self.assertEqual((mode, path), ("managed", MANAGED))

    def test_nothing_anywhere_means_clone(self):
        mode, path = up.pick_source({}, SUITE, fake_is())
        self.assertEqual((mode, path), ("clone", MANAGED))

    def test_legacy_state_without_source_uses_managed(self):
        mode, path = up.pick_source({"version": "0.2.1"}, SUITE, fake_is(MANAGED))
        self.assertEqual((mode, path), ("managed", MANAGED))


class TestRunUpgrade(unittest.TestCase):
    def test_clone_then_install_when_no_source(self):
        calls = []

        def runner(cmd):
            calls.append(cmd)
            return 0

        code = up.run_upgrade("/home/x/.hermes", SUITE, runner=runner)
        self.assertEqual(code, 0)
        self.assertEqual(calls[0][:2], ["git", "clone"])
        self.assertEqual(calls[1][1:], [os.path.join(MANAGED, "scripts", "install.py"),
                                        "--home", "/home/x/.hermes"])

    def test_pull_failure_stops_before_install(self):
        calls = []

        def runner(cmd):
            calls.append(cmd)
            return 1 if cmd[0] == "git" else 0

        import json as _json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            suite = os.path.join(tmp, "superagent")
            os.makedirs(os.path.join(suite, "src", "scripts"))
            open(os.path.join(suite, "src", "scripts", "install.py"), "w").close()
            with open(os.path.join(suite, "state.json"), "w") as fh:
                _json.dump({"source_repo": "/gone"}, fh)
            code = up.run_upgrade(tmp, suite, runner=runner)
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1)  # only the pull, never the install

    def test_installer_exit_code_passes_through(self):
        def runner(cmd):
            return 0 if cmd[0] == "git" else 3

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            suite = os.path.join(tmp, "superagent")
            os.makedirs(os.path.join(suite, "src", "scripts"))
            open(os.path.join(suite, "src", "scripts", "install.py"), "w").close()
            code = up.run_upgrade(tmp, suite, runner=runner)
        self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()
