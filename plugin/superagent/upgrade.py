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
import subprocess
import sys

DEFAULT_REPO_URL = "https://github.com/hezberg/hermes-superagent.git"


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
            print(f"克隆源码失败（{url}）——检查网络后重试，或手动 clone 后跑其中的 install.sh。")
            return code
    else:
        code = runner(["git", "-C", path, "pull", "--ff-only"])
        if code != 0:
            print("git pull 没成功（可能有本地改动或网络问题），升级停在这里，"
                  "现有安装未受影响。处理好后重新运行 hermes superagent upgrade。")
            return code
    installer = os.path.join(path, "scripts", "install.py")
    return runner([sys.executable, installer, "--home", home])
