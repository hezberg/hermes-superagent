#!/usr/bin/env python3
"""hermes-superagent uninstaller — state-driven.

Removes exactly what the install state records: the plugin, the
rendered profiles, the reminder tick script, the previous-generation
snapshot, and the state files themselves. The operator's own data —
suite config, journal, reminder ledger, outbox, backups — is KEPT by
default (it is theirs, and a reinstall picks it back up). `--purge`
removes that too. Hermes' own files are never touched.

Usage: uninstall.py [--purge] [--dry-run] [--home PATH]
"""
import argparse
import json
import os
import shutil
import sys


def say(msg=""):
    print(msg)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="uninstall.py")
    parser.add_argument("--purge", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--home", default=None)
    args = parser.parse_args(argv)

    home = args.home or os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    suite_dir = os.path.join(home, "superagent")

    state = None
    for name in ("state.json", "manifest.json"):
        try:
            with open(os.path.join(suite_dir, name), encoding="utf-8") as fh:
                state = json.load(fh)
            break
        except Exception:
            continue
    if state is None:
        say(f"没有安装记录（{suite_dir} 下没有 state.json / manifest.json），无从卸载。")
        say("若是手动残局，可检查这几处：~/.hermes/plugins/superagent、"
            "~/.hermes/profiles/sa-*、~/.hermes/scripts/superagent-reminder-tick.py。")
        return 1

    targets = []
    for path in state.get("created_paths", []):
        if os.path.abspath(path) == os.path.abspath(suite_dir):
            continue  # the suite dir holds user data; handled separately
        targets.append(path)
    targets.append(os.path.join(suite_dir, "prev"))
    targets.append(os.path.join(suite_dir, "state.json"))
    targets.append(os.path.join(suite_dir, "manifest.json"))

    removed = []
    for path in targets:
        if not os.path.exists(path):
            continue
        if args.dry_run:
            say(f"[dry-run] remove {path}")
        elif os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        removed.append(path)

    if args.purge:
        if os.path.isdir(suite_dir) and not args.dry_run:
            shutil.rmtree(suite_dir)
        say("已彻底清除，包括你的配置与全部历史记录。")
    else:
        kept = [n for n in ("superagent.yaml", "journal.md", "journal.jsonl",
                            "reminders.json", "outbox.json", "backups")
                if os.path.exists(os.path.join(suite_dir, n))]
        if kept:
            say(f"保留了你的数据（{', '.join(kept)}）在 {suite_dir} —— "
                "重装会自动接回；要彻底删除用 uninstall --purge。")
    say(f"卸载完成，共移除 {len(removed)} 项。Hermes 本身未做任何改动。")
    say("提醒：若注册过提醒 cron，请在 hermes cron list 里删掉 superagent-reminder-tick 那条。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
