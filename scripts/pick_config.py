#!/usr/bin/env python3
"""Choose which superagent.yaml an install should use.

Rule (docs/PRINCIPLES.md #5 — configuration must survive being a
user): once the installed copy under $HERMES_HOME/superagent/ has
real values, it wins over any repo-side candidate. That is the file
the user actually maintains; repo files are first-install staging,
and a `git pull` must never get to fight over the real config (a
locally edited tracked template blocks every merge — this happened
in the field on 2026-11-01, twice).

Prints the chosen path on stdout; when the installed copy wins, a
human-readable note goes to stderr.

Usage: pick_config.py <repo-config> <installed-config>
"""
import sys

try:
    import yaml
except ImportError:
    print(sys.argv[1] if len(sys.argv) > 1 else "")
    sys.exit(0)


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


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except Exception:
        return None


def choose(repo_path, suite_path):
    """The installed copy is the source of truth once it holds real
    values: it wins over ANY repo-side candidate — pristine template
    or a filled staging file alike. Repo files are for staging the
    first install only; afterwards, living in the repo tree means
    living where `git pull` can fight over the file."""
    suite_cfg = load(suite_path)
    if suite_cfg is not None and not is_pristine(suite_cfg):
        return suite_path, True
    return repo_path, False


def main(argv):
    if len(argv) != 3:
        print("usage: pick_config.py <repo-config> <installed-config>", file=sys.stderr)
        return 2
    chosen, from_suite = choose(argv[1], argv[2])
    if from_suite:
        print(
            "note: 改用你已填好的那份配置："
            + chosen
            + "（它在 ~/.hermes 下，不在仓库里，git pull 永远碰不到它；以后改配置就改这份）",
            file=sys.stderr,
        )
    print(chosen)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
