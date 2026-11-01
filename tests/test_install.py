import copy
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


class TestNoPyYaml(InstallerCase):
    """The installer must survive an interpreter with no PyYAML —
    Hermes' bundled python is one, and it killed real upgrades
    (the plugin's upgrade command launches the installer with it).
    A blocker module named yaml.py shadows the real one via
    PYTHONPATH and raises ImportError on import."""

    def test_full_install_with_yaml_blocked(self):
        blocker = os.path.join(self.tmp.name, "blocker")
        os.makedirs(blocker)
        with open(os.path.join(blocker, "yaml.py"), "w") as fh:
            fh.write("raise ImportError('blocked for test')\n")
        self.env["PYTHONPATH"] = blocker
        seed = os.path.join(self.tmp.name, "seed.yaml")
        with open(seed, "w") as fh:
            yaml.safe_dump(FILLED, fh)
        result = self.run_install("--config", seed)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Installed:", result.stdout)
        # The rendered profile config is real YAML, parseable here.
        with open(os.path.join(self.home, "profiles", "sa-router",
                               "config.yaml")) as fh:
            rendered = yaml.safe_load(fh)
        self.assertEqual(rendered["model"]["default"], "deepseek-v4.1-flash")


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


class TestZeroConfigInheritance(InstallerCase):
    """The operator's design rule: a working default Hermes profile
    is enough. First install with a pristine suite template must
    proceed in ONE run — roles inherit the default model block
    verbatim, and the installer plants the key into each profile's
    .env itself (no manual script, ever)."""

    def write_default_config(self):
        with open(os.path.join(self.home, "config.yaml"), "w") as fh:
            yaml.safe_dump({
                "model": {
                    "provider": "custom",
                    "default": "cn:deepseek-v4.1-flash",
                    "base_url": "http://100.64.0.1:3001/v1",
                    "api_key_env": "SUPERAGENT_MAIN_API_KEY",
                }
            }, fh)

    def test_first_install_inherits_and_syncs_keys(self):
        self.write_default_config()
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Inheriting the default profile's model", result.stdout)
        router_dir = os.path.join(self.home, "profiles", "sa-router")
        with open(os.path.join(router_dir, "config.yaml")) as fh:
            rendered = yaml.safe_load(fh)
        self.assertEqual(rendered["model"]["default"], "cn:deepseek-v4.1-flash")
        self.assertEqual(rendered["model"]["provider"], "custom")
        self.assertEqual(rendered["model"]["base_url"],
                         "http://100.64.0.1:3001/v1")
        with open(os.path.join(self.home, ".env")) as fh:
            global_line = fh.read().strip()
        with open(os.path.join(router_dir, ".env")) as fh:
            self.assertIn(global_line, fh.read())
        # Idempotent: nothing left to change on the second run.
        result = self.run_install()
        self.assertIn("Changed: nothing", result.stdout)


class TestProfilesAreLivingDirs(InstallerCase):
    """Field failure, 2026-11-01: profile convergence replaced the
    whole directory tree, deleting each profile's .env (with the API
    key) on every config change. The profile then failed every model
    request ('request_failed') while the global .env masked the
    loss. Profiles must converge per-file, never wholesale."""

    def test_env_and_sessions_survive_a_config_change_reinstall(self):
        self.install_filled()
        router_dir = os.path.join(self.home, "profiles", "sa-router")
        env_path = os.path.join(router_dir, ".env")
        with open(env_path, "w") as fh:
            fh.write("SUPERAGENT_MAIN_API_KEY=sk-live\nOTHER_TOKEN=keep-me\n")
        session = os.path.join(router_dir, "sessions", "s1.json")
        os.makedirs(os.path.dirname(session))
        with open(session, "w") as fh:
            fh.write("{}")
        # Change the config so the render really changes.
        with open(self.suite_cfg_path()) as fh:
            cfg = yaml.safe_load(fh)
        cfg["security"]["allow_private_urls"] = False
        with open(self.suite_cfg_path(), "w") as fh:
            yaml.safe_dump(cfg, fh)
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with open(env_path) as fh:
            env_lines = fh.read().splitlines()
        # Unmanaged lines and the file itself survive untouched;
        # the suite-managed key converges onto the global .env.
        self.assertTrue(any(ln.startswith("OTHER_TOKEN=") for ln in env_lines))
        with open(os.path.join(self.home, ".env")) as fh:
            global_line = fh.read().strip()
        self.assertIn(global_line, env_lines)
        self.assertTrue(os.path.isfile(session))
        with open(os.path.join(router_dir, "config.yaml")) as fh:
            self.assertNotIn("allow_private_urls", fh.read())
        # And a further no-change run reports nothing changed.
        result = self.run_install()
        self.assertIn("Changed: nothing", result.stdout)


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
            os.path.join(self.home, "profiles", "sa-router", "config.yaml")))
        # The profile dir itself may remain: key sync planted a .env
        # there during install, and a profile's .env is the operator's
        # property, never removed by uninstall.
        router_dir = os.path.join(self.home, "profiles", "sa-router")
        if os.path.isdir(router_dir):
            self.assertEqual(os.listdir(router_dir), [".env"])
        self.assertTrue(os.path.isfile(self.suite_cfg_path()))
        self.assertTrue(os.path.isfile(journal))
        # state is gone, so a second uninstall has nothing to go on
        self.assertEqual(self.run_uninstall().returncode, 1)

    def test_uninstall_keeps_profile_env_and_sessions(self):
        self.install_filled()
        router_dir = os.path.join(self.home, "profiles", "sa-router")
        env_path = os.path.join(router_dir, ".env")
        with open(env_path, "w") as fh:
            fh.write("SUPERAGENT_MAIN_API_KEY=sk-live\n")
        result = self.run_uninstall()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(os.path.exists(os.path.join(router_dir, "config.yaml")))
        self.assertTrue(os.path.isfile(env_path))


if __name__ == "__main__":
    unittest.main()


class TestKeyRotation(InstallerCase):
    """Rotating the key in the global .env is a one-file edit: the
    global file is the single source of truth, and every profile
    copy converges onto it on the next install — including a copy
    someone hand-edited, which is a stale copy, not a preference."""

    def set_global_key(self, value):
        with open(os.path.join(self.home, ".env"), "w") as fh:
            fh.write(f"SUPERAGENT_MAIN_API_KEY={value}\n")

    def profile_key(self, profile):
        path = os.path.join(self.home, "profiles", profile, ".env")
        if not os.path.isfile(path):
            return None
        with open(path) as fh:
            for line in fh:
                if line.startswith("SUPERAGENT_MAIN_API_KEY="):
                    return line.strip().split("=", 1)[1]
        return None

    def test_synced_copies_follow_a_global_rotation(self):
        self.install_filled()
        self.assertTrue(self.profile_key("sa-router"))
        self.set_global_key("sk-ROTATED-KEY")
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.profile_key("sa-router"), "sk-ROTATED-KEY")
        self.assertEqual(self.profile_key("sa-worker-general"), "sk-ROTATED-KEY")

    def test_profile_values_converge_to_the_global_key(self):
        self.install_filled()
        path = os.path.join(self.home, "profiles", "sa-router", ".env")
        with open(path) as fh:
            body = fh.read()
        planted = self.profile_key("sa-router")
        self.assertTrue(planted)
        with open(path, "w") as fh:
            fh.write(body.replace(planted, "sk-HAND-EDITED"))
        self.set_global_key("sk-ROTATED-KEY")
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.profile_key("sa-router"), "sk-ROTATED-KEY")
        self.assertEqual(self.profile_key("sa-worker-general"), "sk-ROTATED-KEY")

    def test_state_records_hashes_not_values(self):
        self.install_filled()
        with open(os.path.join(self.home, "superagent", "state.json")) as fh:
            raw = fh.read()
        state = json.loads(raw)
        digest = state["synced_keys"]["sa-router"]["SUPERAGENT_MAIN_API_KEY"]
        self.assertEqual(len(digest), 64)
        self.assertNotIn(self.profile_key("sa-router"), raw)


class TestSelectionInstall(InstallerCase):
    """The 0.7 doctrine end-to-end: superagent.yaml holds ONLY
    selections; providers/models come from the default Hermes
    config, named entries are copied into the rendered profiles
    (Hermes' own seeding rule), and keys converge from the global
    .env using the variable the ENTRY declares."""

    def write_default_config(self):
        with open(os.path.join(self.home, "config.yaml"), "w") as fh:
            yaml.safe_dump({
                "model": {"provider": "custom", "default": "base-model",
                          "base_url": "http://100.64.0.1:3001/v1",
                          "api_key_env": "SUPERAGENT_MAIN_API_KEY"},
                "custom_providers": [
                    {"name": "lab", "base_url": "http://127.0.0.1:3001/v1",
                     "key_env": "LAB_KEY"},
                ],
            }, fh)
        with open(os.path.join(self.home, ".env"), "a") as fh:
            fh.write("LAB_KEY=sk-lab-value\n")

    def selection_cfg(self):
        cfg = copy.deepcopy(FILLED)
        cfg.pop("providers", None)
        cfg["router"].update({"provider": "", "model": ""})
        for w in cfg["workers"]:
            w.update({"provider": "", "model": ""})
        deep = [w for w in cfg["workers"] if w["profile"] == "sa-worker-research"][0]
        deep.update({"provider": "lab", "model": "lab-model"})
        return cfg

    def test_selection_install_renders_entry_and_syncs_its_key(self):
        self.write_default_config()
        self.write_suite_config(self.selection_cfg())
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        deep_dir = os.path.join(self.home, "profiles", "sa-worker-research")
        with open(os.path.join(deep_dir, "config.yaml")) as fh:
            rendered = yaml.safe_load(fh)
        self.assertEqual(rendered["model"]["provider"], "custom:lab")
        self.assertEqual(rendered["model"]["default"], "lab-model")
        self.assertEqual(rendered["custom_providers"][0]["name"], "lab")
        with open(os.path.join(deep_dir, ".env")) as fh:
            self.assertIn("LAB_KEY=sk-lab-value", fh.read())
        # the router inherited the default block as before
        router_dir = os.path.join(self.home, "profiles", "sa-router")
        with open(os.path.join(router_dir, "config.yaml")) as fh:
            router_cfg = yaml.safe_load(fh)
        self.assertEqual(router_cfg["model"]["default"], "base-model")

    def test_unknown_selection_fails_with_the_menu(self):
        self.write_default_config()
        cfg = self.selection_cfg()
        deep = [w for w in cfg["workers"] if w["profile"] == "sa-worker-research"][0]
        deep.update({"provider": "nope"})
        self.write_suite_config(cfg)
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("custom:lab", result.stdout)
        self.assertIn("not in your Hermes config", result.stdout)


class TestEnvFormats(InstallerCase):
    def test_export_and_quoted_global_key_is_found(self):
        with open(os.path.join(self.home, ".env"), "w") as fh:
            fh.write('export SUPERAGENT_MAIN_API_KEY="sk-quoted-value"\n')
        self.install_filled()
        path = os.path.join(self.home, "profiles", "sa-router", ".env")
        with open(path) as fh:
            self.assertIn("SUPERAGENT_MAIN_API_KEY=sk-quoted-value", fh.read())

    def test_missing_key_message_diagnoses_and_never_asks_for_a_rerun(self):
        with open(os.path.join(self.home, ".env"), "w") as fh:
            fh.write("# no keys here\n")
        self.write_suite_config()
        result = self.run_install()
        self.assertIn("no line for SUPERAGENT_MAIN_API_KEY exists", result.stdout)
        self.assertNotIn("then re-run", result.stdout)
        # and it does not tell the operator to go use the Router yet
        self.assertIn("cannot call a model until", result.stdout)
        self.assertNotIn("give the Router a task", result.stdout)

    def test_empty_value_line_is_diagnosed_as_empty(self):
        with open(os.path.join(self.home, ".env"), "w") as fh:
            fh.write("SUPERAGENT_MAIN_API_KEY=\n")
        self.write_suite_config()
        result = self.run_install()
        self.assertIn("its value is empty", result.stdout)

    def test_fullwidth_equals_key_is_found(self):
        with open(os.path.join(self.home, ".env"), "w", encoding="utf-8") as fh:
            fh.write("SUPERAGENT_MAIN_API_KEY＝sk-fullwidth\n")
        self.install_filled()
        path = os.path.join(self.home, "profiles", "sa-router", ".env")
        with open(path) as fh:
            self.assertIn("SUPERAGENT_MAIN_API_KEY=sk-fullwidth", fh.read())


class TestDayOne(InstallerCase):
    """The out-of-box contract: a fresh machine whose default Hermes
    profile already works installs in ONE run — no next-step about
    keys, no hard errors, every profile holding the key."""

    def test_fresh_machine_one_run(self):
        with open(os.path.join(self.home, "config.yaml"), "w") as fh:
            yaml.safe_dump({
                "model": {"provider": "custom", "default": "base-model",
                          "base_url": "http://100.64.0.1:3001/v1",
                          "api_key_env": "SUPERAGENT_MAIN_API_KEY"},
            }, fh)
        # No suite config anywhere — and because the default profile
        # already has a model, the FIRST run completes the install.
        second = self.run_install()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertNotIn("no line for SUPERAGENT_MAIN_API_KEY", second.stdout)
        self.assertNotIn("WARNING: postflight", second.stdout)
        self.assertIn("Finish with: hermes gateway restart", second.stdout)
        for profile in ("sa-router", "sa-worker-general", "sa-worker-research"):
            with open(os.path.join(self.home, "profiles", profile, ".env")) as fh:
                self.assertIn("SUPERAGENT_MAIN_API_KEY=", fh.read())
