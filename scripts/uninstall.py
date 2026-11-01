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
        say(f"No install record (no state.json / manifest.json under {suite_dir}); nothing to uninstall.")
        say("For a manual leftover, check: ~/.hermes/plugins/superagent, "
            "~/.hermes/profiles/sa-*, ~/.hermes/scripts/superagent-reminder-tick.py.")
        return 1

    targets = []
    for path in state.get("created_paths", []):
        if os.path.abspath(path) == os.path.abspath(suite_dir):
            continue  # the suite dir holds user data; handled separately
        targets.append(path)
    targets.append(os.path.join(suite_dir, "prev"))
    targets.append(os.path.join(suite_dir, "state.json"))
    targets.append(os.path.join(suite_dir, "manifest.json"))

    profile_dirs = {
        os.path.abspath(os.path.join(home, "profiles", p))
        for p in state.get("profiles", [])
    }
    managed = state.get("files") or {}

    def is_protected(rel):
        parts = rel.replace(os.sep, "/").split("/")
        return parts[-1] == ".env" or parts[0] in ("sessions", "logs", "memory")

    removed = []
    kept_profiles = []
    for path in targets:
        if not os.path.exists(path):
            continue
        if os.path.abspath(path) in profile_dirs and os.path.isdir(path):
            # A profile directory is a living directory: remove only
            # the files the suite manages. The operator's own files
            # (.env, sessions, logs, memory) are not suite property,
            # and legacy states that recorded them are overridden.
            name = os.path.basename(path)
            for rel in (managed.get(f"profile:{name}") or {}):
                if is_protected(rel):
                    continue
                fp = os.path.join(path, rel)
                if os.path.isfile(fp):
                    if args.dry_run:
                        say(f"[dry-run] remove {fp}")
                    else:
                        os.remove(fp)
                    removed.append(fp)
            if not args.dry_run:
                def prune(d):
                    for entry in os.listdir(d):
                        full = os.path.join(d, entry)
                        if os.path.isdir(full):
                            prune(full)
                    if d != path and not os.listdir(d):
                        os.rmdir(d)

                prune(path)
                if os.path.isdir(path) and not os.listdir(path):
                    os.rmdir(path)
            if os.path.isdir(path) and os.listdir(path):
                kept_profiles.append(name)
            continue
        if args.dry_run:
            say(f"[dry-run] remove {path}")
        elif os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        removed.append(path)
    if kept_profiles:
        say(f"Profile directories kept (they hold your own files): {', '.join(kept_profiles)} - "
            "the suite's rendered files were removed; delete the directories by hand if you want them gone.")

    if args.purge:
        if os.path.isdir(suite_dir) and not args.dry_run:
            shutil.rmtree(suite_dir)
        say("Purged: your config and all history are gone too.")
    else:
        kept = [n for n in ("superagent.yaml", "journal.md", "journal.jsonl",
                            "reminders.json", "outbox.json", "backups")
                if os.path.exists(os.path.join(suite_dir, n))]
        if kept:
            say(f"Kept your data ({', '.join(kept)}) in {suite_dir} - "
                "a reinstall picks it back up; use uninstall --purge to delete it.")
    say(f"Uninstall complete: removed {len(removed)} item(s). Hermes itself was not modified.")
    say("Note: if a reminder cron job was registered, delete the superagent-reminder-tick entry in hermes cron list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
