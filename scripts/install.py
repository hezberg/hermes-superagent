#!/usr/bin/env python3
"""hermes-superagent installer — declarative and idempotent.

One command does fresh install, upgrade, and repair: it computes the
desired state from the repo + the suite config, converges the Hermes
home to it, verifies with the suite's own doctor checks, and reports
what changed. Running it twice changes nothing the second time.

Design rules (learned the hard way, see CHANGELOG 0.5.0):
- The user's config lives ONLY at ~/.hermes/superagent/superagent.yaml.
  The repo ships templates; no user value ever sits in the repo tree,
  so `git pull` can never conflict over it.
- First run with no config is two-phase: the installer writes a
  guided template to the suite path and stops (exit 3). Fill it in,
  run the same command again.
- VERSION (repo root) is the only version source; the installer
  stamps it into the installed plugin copy.
- Before changing anything, the previous generation is snapshotted
  to ~/.hermes/superagent/prev/ — `--rollback` restores it.
- state.json records exactly what was installed (paths + hashes);
  the uninstaller removes exactly that, nothing else.

Usage:
  install.py [--config PATH] [--dry-run] [--rollback]
Exit codes: 0 ok · 1 hard failure · 2 preflight · 3 config needed.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXIT_OK, EXIT_FAIL, EXIT_PREFLIGHT, EXIT_NEEDS_CONFIG = 0, 1, 2, 3


def say(msg=""):
    print(msg)


def repo_version():
    try:
        with open(os.path.join(REPO, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "0.0.0"


# ------------------------------------------------------------------ config
def is_pristine(cfg):
    """True when nothing user-specific has been filled in yet."""
    if not isinstance(cfg, dict):
        return True
    for provider in (cfg.get("providers") or {}).values():
        if isinstance(provider, dict) and provider.get("base_url"):
            return False
    roles = [cfg.get("router") or {}] + list(cfg.get("workers") or [])
    for role in roles:
        if isinstance(role, dict) and role.get("model"):
            return False
    return True


def load_yaml(path):
    import yaml

    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ------------------------------------------------------------------ trees
def tree_hashes(root, skip_topdirs=()):
    """{relative path: sha256} for every file under root ({} if absent).
    Top-level directories named in skip_topdirs are excluded (the
    profile skills/ subtree is managed as its own resource)."""
    out = {}
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            dirnames[:] = [d for d in dirnames if d not in skip_topdirs]
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            with open(full, "rb") as fh:
                out[rel] = hashlib.sha256(fh.read()).hexdigest()
    return out


def replace_tree(src, dst, preserve_topdirs=()):
    """Replace dst with src, keeping any preserved top-level subdirs
    of dst (they belong to other resources)."""
    kept = {}
    for name in preserve_topdirs:
        existing = os.path.join(dst, name)
        if os.path.isdir(existing):
            kept[name] = existing
    stash = None
    if kept:
        stash = tempfile.mkdtemp(prefix="preserve-")
        for name, path in kept.items():
            shutil.move(path, os.path.join(stash, name))
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    if stash:
        for name in kept:
            src_kept = os.path.join(stash, name)
            if os.path.isdir(src_kept):
                shutil.move(src_kept, os.path.join(dst, name))
        shutil.rmtree(stash, ignore_errors=True)


# ------------------------------------------------------------------ hermes
def run_hermes(args, dry_run=False):
    """Best-effort Hermes CLI call. Returns True on success."""
    if dry_run:
        say(f"[dry-run] hermes {' '.join(args)}")
        return True
    try:
        result = subprocess.run(
            ["hermes"] + args, capture_output=True, text=True, timeout=60
        )
        return result.returncode == 0
    except Exception:
        return False


def hermes_output(args):
    try:
        result = subprocess.run(
            ["hermes"] + args, capture_output=True, text=True, timeout=60
        )
        return result.stdout or ""
    except Exception:
        return ""


# ------------------------------------------------------------------ state
def state_path(home):
    return os.path.join(home, "superagent", "state.json")


def read_state(home):
    for name in ("state.json", "manifest.json"):
        path = os.path.join(home, "superagent", name)
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            continue
    return None


def snapshot_prev(home, state):
    """Copy the current generation into superagent/prev/ (one deep)."""
    prev = os.path.join(home, "superagent", "prev")
    if os.path.isdir(prev):
        shutil.rmtree(prev)
    os.makedirs(prev, exist_ok=True)
    paths = []
    if state:
        paths = state.get("created_paths") or list(
            (state.get("files") or {}).keys()
        )
    # Code artifacts only — never the suite dir itself: a rollback
    # must not rewind the user's config, journal, or reminder ledger.
    candidates = {
        os.path.join(home, "plugins", "superagent"),
        os.path.join(home, "scripts", "superagent-reminder-tick.py"),
        os.path.join(home, "superagent", "state.json"),
        os.path.join(home, "superagent", "manifest.json"),
    }
    profiles = (state or {}).get("profiles") or []
    for profile in profiles:
        candidates.add(os.path.join(home, "profiles", profile))
    # Legacy manifests carry no profile list; recover the profile
    # dirs from their created_paths instead.
    for path in paths:
        if os.path.basename(os.path.dirname(path)) == "profiles":
            candidates.add(path)
    manifest = {"version": (state or {}).get("version"), "paths": []}
    for path in sorted(candidates):
        if not os.path.exists(path):
            continue
        rel = os.path.relpath(path, home)
        dst = os.path.join(prev, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(path):
            shutil.copytree(path, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(path, dst)
        manifest["paths"].append(rel)
    with open(os.path.join(prev, "prev.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
    return manifest["version"]


def do_rollback(home):
    prev = os.path.join(home, "superagent", "prev")
    meta_path = os.path.join(prev, "prev.json")
    if not os.path.isfile(meta_path):
        say("没有可回滚的上一代快照（先成功安装过一次才会有）。")
        return EXIT_FAIL
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    for rel in meta.get("paths", []):
        src = os.path.join(prev, rel)
        dst = os.path.join(home, rel)
        if os.path.isdir(src):
            replace_tree(src, dst)
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
    say(f"已回滚到上一代（版本 {meta.get('version') or '未知'}）。"
        "重启 gateway 后生效：hermes gateway restart")
    return EXIT_OK


# ------------------------------------------------------------------ config
def resolve_config(home, explicit, dry_run):
    """Return (suite_cfg_path, cfg_dict) or stop the world politely.

    The suite path is the only home a user config ever gets. An
    explicit --config seeds it when absent; when a suite config
    already exists it is the truth and --config is ignored (said out
    loud). Absent both, phase one: write the guided template and
    stop with EXIT_NEEDS_CONFIG.
    """
    suite_dir = os.path.join(home, "superagent")
    suite_cfg = os.path.join(suite_dir, "superagent.yaml")

    if os.path.isfile(suite_cfg):
        cfg = load_yaml(suite_cfg)
        if is_pristine(cfg):
            # A pristine suite file is a leftover phase-one template.
            # A filled --config reseeds it; otherwise, stop politely.
            if explicit and os.path.isfile(explicit):
                seeded = load_yaml(explicit)
                if not is_pristine(seeded):
                    if not dry_run:
                        shutil.copy2(explicit, suite_cfg)
                    say("已用 --config 提供的配置覆盖那份空模板。")
                    return suite_cfg, seeded, EXIT_OK
            say("配置还没填：~/.hermes/superagent/superagent.yaml 里还没有"
                "任何 provider 地址或模型。填好后重新运行同一条命令即可。")
            return None, None, EXIT_NEEDS_CONFIG
        if explicit and os.path.abspath(explicit) != os.path.abspath(suite_cfg):
            say("note: 已存在生效配置 ~/.hermes/superagent/superagent.yaml，"
                "以它为准（--config 只在首次安装时用来播种）。")
        return suite_cfg, cfg, EXIT_OK

    if explicit:
        if not os.path.isfile(explicit):
            say(f"ERROR: --config 指定的文件不存在：{explicit}")
            return None, None, EXIT_PREFLIGHT
        cfg = load_yaml(explicit)
        if is_pristine(cfg):
            say("这份 --config 还是空模板，先填好 provider 和模型再安装。")
            return None, None, EXIT_NEEDS_CONFIG
        if not dry_run:
            os.makedirs(suite_dir, exist_ok=True)
            shutil.copy2(explicit, suite_cfg)
        say(f"已把配置播种到 {suite_cfg} —— 以后改配置只改这份。")
        return suite_cfg, cfg, EXIT_OK

    template = os.path.join(REPO, "config", "superagent.yaml")
    if not dry_run:
        os.makedirs(suite_dir, exist_ok=True)
        shutil.copy2(template, suite_cfg)
    say("第一次安装，先生成你的配置文件：")
    say(f"  {suite_cfg}")
    say("在里面填上 provider 的 base_url 和每个角色的模型（文件里有注释），"
        "然后重新运行同一条命令。仓库里不会留下任何你的配置，git pull 永远不会和它冲突。")
    return None, None, EXIT_NEEDS_CONFIG


# ------------------------------------------------------------------ install
def stamp_version(plugin_dst, version):
    """Write the release version into the installed plugin copy."""
    init_py = os.path.join(plugin_dst, "__init__.py")
    try:
        with open(init_py, encoding="utf-8") as fh:
            text = fh.read()
        import re

        text = re.sub(
            r'^PLUGIN_VERSION = ".*"$', f'PLUGIN_VERSION = "{version}"',
            text, flags=re.M,
        )
        with open(init_py, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError:
        pass
    yaml_path = os.path.join(plugin_dst, "plugin.yaml")
    try:
        with open(yaml_path, encoding="utf-8") as fh:
            text = fh.read()
        import re

        text = re.sub(r"^version: .*$", f"version: {version}", text, flags=re.M)
        with open(yaml_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(prog="install.py")
    parser.add_argument("--config", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--home", default=None,
                        help="Hermes home (default: $HERMES_HOME or ~/.hermes)")
    args = parser.parse_args(argv)

    home = args.home or os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    version = repo_version()

    if args.rollback:
        return do_rollback(home)

    # ------------------------------------------------------------ preflight
    if not os.path.isdir(home):
        say(f"ERROR: Hermes home 不存在（{home}）。先运行一次 Hermes。")
        return EXIT_PREFLIGHT
    if shutil.which("hermes") is None and not args.dry_run:
        say("ERROR: 找不到 hermes 命令。这个套件是 Hermes 的附加层，不自带 Hermes。")
        return EXIT_PREFLIGHT
    try:
        import yaml  # noqa: F401
    except ImportError:
        say("ERROR: 当前 python3 没有 PyYAML（Hermes 自带的那份即可）。")
        return EXIT_PREFLIGHT

    suite_cfg, cfg, code = resolve_config(home, args.config, args.dry_run)
    if suite_cfg is None:
        return code

    # ------------------------------------------------------------ validate
    result = subprocess.run(
        [sys.executable, os.path.join(REPO, "scripts", "validate_config.py"), suite_cfg],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        say("配置校验没过，先修这几处（都在 ~/.hermes/superagent/superagent.yaml 里）：")
        say((result.stdout or "") + (result.stderr or ""))
        return EXIT_FAIL

    router = (cfg.get("router") or {}).get("profile")
    workers = [w.get("profile") for w in cfg.get("workers") or []]
    profiles = [p for p in [router] + workers if p]
    suite_dir = os.path.join(home, "superagent")

    old_state = read_state(home)
    old_version = (old_state or {}).get("version")
    if not args.dry_run and old_state:
        snapshot_prev(home, old_state)

    changes = []

    def converge_file(src_bytes, dst, label):
        old = None
        if os.path.isfile(dst):
            with open(dst, "rb") as fh:
                old = fh.read()
        if old == src_bytes:
            return "unchanged"
        if not args.dry_run:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as fh:
                fh.write(src_bytes)
        changes.append(label)
        return "updated"

    def converge_tree(src_dir, dst, label, preserve=()):
        if tree_hashes(src_dir, skip_topdirs=preserve) == \
                tree_hashes(dst, skip_topdirs=preserve):
            return "unchanged"
        if not args.dry_run:
            replace_tree(src_dir, dst, preserve_topdirs=preserve)
        changes.append(label)
        return "updated"

    # ------------------------------------------------------------ resources
    plugin_src = os.path.join(REPO, "plugin", "superagent")
    plugin_dst = os.path.join(home, "plugins", "superagent")
    with tempfile.TemporaryDirectory() as tmp:
        staged_plugin = os.path.join(tmp, "plugin")
        shutil.copytree(plugin_src, staged_plugin,
                        ignore=shutil.ignore_patterns("__pycache__"))
        stamp_version(staged_plugin, version)
        plugin_status = converge_tree(staged_plugin, plugin_dst, "插件")

        rendered = os.path.join(tmp, "profiles")
        r = subprocess.run(
            [sys.executable, os.path.join(REPO, "scripts", "render_profiles.py"),
             "--config", suite_cfg, "--templates", os.path.join(REPO, "profiles"),
             "--out", rendered],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            say("渲染 profile 失败：")
            say((r.stdout or "") + (r.stderr or ""))
            return EXIT_FAIL
        profile_status = {}
        for profile in profiles:
            profile_status[profile] = converge_tree(
                os.path.join(rendered, profile),
                os.path.join(home, "profiles", profile),
                f"profile {profile}",
                preserve=("skills",),
            )

    # skills ride inside the profiles but are not part of the render
    skill_map = [(router, "router")]
    skill_map += [(w, "worker") for w in workers]
    for profile, kind in skill_map:
        if not profile:
            continue
        src = os.path.join(REPO, "plugin", "superagent", "skills", kind, "SKILL.md")
        dst = os.path.join(home, "profiles", profile, "skills",
                           f"{kind}-superagent", "SKILL.md")
        with open(src, "rb") as fh:
            converge_file(fh.read(), dst, f"{kind} skill ({profile})")

    tick_src = os.path.join(REPO, "scripts", "reminder_tick.py")
    with open(tick_src, encoding="utf-8") as fh:
        tick_bytes = fh.read().replace("__HERMES_HOME__", home).encode("utf-8")
    tick_dst = os.path.join(home, "scripts", "superagent-reminder-tick.py")
    tick_status = converge_file(tick_bytes, tick_dst, "提醒脚本")
    if tick_status == "updated" and not args.dry_run:
        os.chmod(tick_dst, 0o755)

    # ------------------------------------------------------------ ensures
    ensures = []
    ensures.append(("插件启用", run_hermes(["plugins", "enable", "superagent"], args.dry_run)))
    ensures.append(("Router kanban（cli）",
                    run_hermes(["-p", router, "tools", "enable", "kanban"], args.dry_run)))
    ensures.append(("Router kanban（feishu）",
                    run_hermes(["-p", router, "tools", "enable", "kanban",
                                "--platform", "feishu"], args.dry_run)))
    cron_list = hermes_output(["cron", "list"]) if not args.dry_run else ""
    cron_present = "superagent-reminder-tick" in cron_list
    cron_created = False
    if not cron_present and not args.dry_run:
        cron_created = run_hermes(
            ["cron", "create", "every 10m", "--no-agent",
             "--script", "superagent-reminder-tick.py"])
        cron_present = cron_created
    ensures.append(("提醒 cron", cron_present))

    # ------------------------------------------------------------ state
    files = {"plugin": tree_hashes(plugin_dst)}
    for profile in profiles:
        files[f"profile:{profile}"] = tree_hashes(
            os.path.join(home, "profiles", profile), skip_topdirs=("skills",))
    created_paths = [plugin_dst, suite_dir, tick_dst] + [
        os.path.join(home, "profiles", p) for p in profiles
    ]
    state = {
        "suite": "hermes-superagent",
        "version": version,
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hermes_home": home,
        "profiles": profiles,
        "router": router,
        "files": files,
        "created_paths": created_paths,
    }
    if not args.dry_run:
        os.makedirs(suite_dir, exist_ok=True)
        with open(state_path(home), "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1, ensure_ascii=False)
        # legacy manifest, kept for older tooling and doctor's drift check
        with open(os.path.join(suite_dir, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1, ensure_ascii=False)

    # ------------------------------------------------------------ postflight
    hard_errors, next_steps = postflight(home, args.dry_run)

    # ------------------------------------------------------------ summary
    say("")
    if old_version and old_version != version:
        say(f"升级完成：{old_version} → {version}")
    elif old_version:
        say(f"已是最新（{version}），本次为收敛检查")
    else:
        say(f"安装完成：{version}")
    if changes:
        say("本次变更：" + "、".join(changes))
    else:
        say("本次变更：无（一切已是期望状态）")
    soft = [name for name, ok in ensures if not ok]
    if soft:
        say("这几步没自动完成，不影响主链路，可稍后手动处理：" + "、".join(soft))
    if cron_created:
        next_steps.append("给提醒 cron 指定投递平台：hermes cron list 找到它，"
                            "再 hermes cron edit <id> --deliver feishu")
    for step in next_steps:
        say(f"下一步：{step}")
    say("收尾：hermes gateway restart —— 然后就能对 Router 派活了。")
    if hard_errors:
        say("")
        say("⚠ 体检发现硬问题，安装不能算完成：")
        for err in hard_errors:
            say(f"  ✗ {err}")
        return EXIT_FAIL
    return EXIT_OK


def postflight(home, dry_run):
    """Run the installed plugin's doctor checks in-process.

    Errors split into hard failures vs operator next-steps (the API
    key line and plugin enablement settle only after the operator's
    own step / a gateway restart, so they never fail an install).
    """
    if dry_run:
        return [], []
    sys.path.insert(0, os.path.join(home, "plugins"))
    os.environ["HERMES_HOME"] = home
    try:
        import superagent as sa

        findings = sa._doctor_findings()
    except Exception:
        return [], []
    hard, steps = [], []
    for f in findings:
        if f.get("level") != "error":
            continue
        text = f.get("text", "")
        if "api_key_env" in text or "plugins.enabled" in text or "名单" in text:
            steps.append(f.get("fix") or text)
        else:
            hard.append(text)
    return hard, steps


if __name__ == "__main__":
    sys.exit(main())
