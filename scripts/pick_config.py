#!/usr/bin/env python3
"""Choose which superagent.yaml an install should use.

Rule (docs/PRINCIPLES.md #5 — configuration must survive being a
user): when the repo copy is still the pristine template (no provider
base_url and no role model filled in) but the installed copy under
$HERMES_HOME/superagent/ has real values, the installed copy wins.
That is the file the user actually filled in; a `git pull` refreshing
the repo template must never silently replace it (this happened in
the field on 2026-11-01 and cost a full re-configuration).

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
    suite_cfg = load(suite_path)
    if suite_cfg is not None and not is_pristine(suite_cfg) and is_pristine(load(repo_path)):
        return suite_path, True
    return repo_path, False


def main(argv):
    if len(argv) != 3:
        print("usage: pick_config.py <repo-config> <installed-config>", file=sys.stderr)
        return 2
    chosen, from_suite = choose(argv[1], argv[2])
    if from_suite:
        print(
            "note: 仓库里的配置还是空模板，改用你已填好的那份："
            + chosen
            + "（以后以这份为准，git pull 不会再冲掉它）",
            file=sys.stderr,
        )
    print(chosen)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
