"""Self-upgrade: `hermes superagent upgrade`.

An installed suite must never depend on the operator remembering
where the source checkout lives (field lesson, 2026-11-01: the
upgrade runbook kept cd-ing into a path that did not exist on the
operator's machine, and every "install" silently never ran).

Source resolution, in order:
  1. the checkout recorded in state.json at install time
     (`source_repo`), if it is still there;
  2. a suite-managed clone at ~/.hermes/superagent/src — cloned from
     `repo_url` on first use, pulled afterwards.

The upgrade itself is just that checkout's installer run against
this Hermes home: one convergence, same as a manual upgrade.
"""
import json
import os
import shutil
import subprocess
import sys

DEFAULT_REPO_URL = "https://github.com/hezberg/hermes-superagent.git"


def pick_python(probe=None):
    """An interpreter that can run the installer (it needs PyYAML).

    The interpreter running this plugin may be Hermes' bundled
    python, which ships no PyYAML (field failure, 2026-11-01: the
    upgrade pulled fine, then the installer died on the import).
    Probe candidates and use the first that imports yaml.
    """
    if probe is None:
        def probe(exe):
            try:
                return subprocess.run(
                    [exe, "-c", "import yaml"],
                    capture_output=True, timeout=15,
                ).returncode == 0
            except Exception:
                return False

    seen = set()
    for cand in (sys.executable, shutil.which("python3"), "/usr/bin/python3"):
        if cand and cand not in seen:
            seen.add(cand)
            if probe(cand):
                return cand
    return sys.executable


def read_state(suite_dir):
    try:
        with open(os.path.join(suite_dir, "state.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def has_installer(path):
    return bool(path) and os.path.isfile(os.path.join(path, "scripts", "install.py"))


def pick_source(state, suite_dir, is_installer_dir=has_installer):
    """Decide where the upgrade's code comes from.

    Returns (mode, path): mode is "recorded" (the install-time
    checkout), "managed" (the suite's own clone, present), or
    "clone" (managed path, needs cloning first).
    """
    recorded = (state or {}).get("source_repo")
    if is_installer_dir(recorded):
        return "recorded", recorded
    managed = os.path.join(suite_dir, "src")
    if is_installer_dir(managed):
        return "managed", managed
    return "clone", managed


def run_upgrade(home, suite_dir, runner=None):
    """Pull (or clone) the source, then run its installer.

    `runner(cmd) -> returncode` is injectable for tests; the default
    streams the child's output through.
    """
    if runner is None:
        def runner(cmd):
            print("+ " + " ".join(cmd))
            return subprocess.run(cmd).returncode

    state = read_state(suite_dir)
    url = state.get("repo_url") or DEFAULT_REPO_URL
    mode, path = pick_source(state, suite_dir)
    if mode == "clone":
        code = runner(["git", "clone", url, path])
        if code != 0:
            print(f"Cloning the source failed ({url}) - check the network and retry, or clone manually and run its install.sh.")
            return code
    else:
        code = runner(["git", "-C", path, "pull", "--ff-only"])
        if code != 0:
            print("git pull did not succeed (local changes or a network problem). The upgrade "
                  "stops here; the current install is untouched. Fix it and re-run hermes superagent upgrade.")
            return code
    installer = os.path.join(path, "scripts", "install.py")
    return runner([pick_python(), installer, "--home", home])
