#!/usr/bin/env python3
"""Validate a hermes-superagent configuration file.

Structural problems are ERRORS (exit 1). Fields the user still has to fill
in (empty base_url / model) are WARNINGS — the shipped template validates
with warnings so you can check the plumbing before choosing models.

Usage: validate_config.py [path-to-superagent.yaml]
"""
import sys

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required (it ships with Hermes itself).", file=sys.stderr)
    sys.exit(2)

PROVIDER_TYPES = {"openai-compatible", "anthropic"}
WATCHDOG_AUTHORITIES = {"report-only", "nudge", "requeue"}
FASTPATH_ACTIONS = {"passthrough", "drop", "slowpath"}
ACCEPT_MODES = {"observe", "auto"}


def validate(cfg):
    errors, warnings = [], []

    def err(msg):
        errors.append(msg)

    def warn(msg):
        warnings.append(msg)

    if not isinstance(cfg, dict):
        return ["config root must be a mapping"], []
    if cfg.get("version") != 1:
        err("version must be 1")

    providers = cfg.get("providers")
    if not isinstance(providers, dict) or not providers:
        err("providers: at least one provider is required")
        providers = {}
    for name, p in providers.items():
        if not isinstance(p, dict):
            err(f"providers.{name}: must be a mapping")
            continue
        if p.get("type") not in PROVIDER_TYPES:
            err(f"providers.{name}.type must be one of {sorted(PROVIDER_TYPES)}")
        if not p.get("api_key_env"):
            err(f"providers.{name}.api_key_env is required (name of the env var holding the key)")
        if not p.get("base_url"):
            warn(f"providers.{name}.base_url is empty — fill it in before installing")

    def check_role(label, role):
        if not isinstance(role, dict):
            err(f"{label}: must be a mapping")
            return
        prov = role.get("provider")
        if prov not in providers:
            err(f"{label}.provider references unknown provider {prov!r}")
        if not role.get("model"):
            warn(f"{label}.model is empty — fill it in before installing")

    check_role("router", cfg.get("router"))

    workers = cfg.get("workers")
    if not isinstance(workers, list) or not workers:
        err("workers: at least one worker is required")
        workers = []
    seen_profiles = set()
    for i, w in enumerate(workers):
        label = f"workers[{i}]"
        check_role(label, w)
        if isinstance(w, dict):
            prof = w.get("profile")
            if not prof:
                err(f"{label}.profile is required")
            elif prof in seen_profiles:
                err(f"{label}.profile {prof!r} is used more than once")
            seen_profiles.add(prof)
            mc = w.get("max_concurrent", 1)
            if not isinstance(mc, int) or mc < 1:
                err(f"{label}.max_concurrent must be a positive integer")

    wd = cfg.get("watchdog") or {}
    if wd.get("authority", "report-only") not in WATCHDOG_AUTHORITIES:
        err(f"watchdog.authority must be one of {sorted(WATCHDOG_AUTHORITIES)}")

    policy = cfg.get("policy")
    if policy is None:
        warn("policy section missing — the Gate will default to observe mode, CLI source only")
    elif not isinstance(policy, dict):
        err("policy: must be a mapping")
    else:
        if policy.get("accept_mode", "observe") not in ACCEPT_MODES:
            err(f"policy.accept_mode must be one of {sorted(ACCEPT_MODES)}")
        sources = policy.get("sources") or {}
        if not isinstance(sources, dict):
            err("policy.sources: must be a mapping of source name to settings")
        else:
            for sname, scfg in sources.items():
                if not isinstance(scfg, dict):
                    err(f"policy.sources.{sname}: must be a mapping")
                elif not isinstance(scfg.get("allowed_senders", []), list):
                    err(f"policy.sources.{sname}.allowed_senders must be a list")
        if not isinstance(policy.get("bots", []), list):
            err("policy.bots must be a list")
        for i, rule in enumerate(policy.get("rules") or []):
            if not isinstance(rule, dict) or not rule.get("id") or not rule.get("instruction"):
                err(f"policy.rules[{i}]: each rule needs an id and an instruction")

    for label, role in [("router", cfg.get("router"))] + [
        (f"workers[{i}]", w) for i, w in enumerate(cfg.get("workers") or [])
    ]:
        if isinstance(role, dict):
            effort = role.get("reasoning_effort")
            if effort is not None and not isinstance(effort, str):
                err(f"{label}.reasoning_effort must be a string (or empty)")

    security = cfg.get("security")
    if security is not None:
        if not isinstance(security, dict):
            err("security: must be a mapping")
        elif "allow_private_urls" in security and not isinstance(
            security["allow_private_urls"], bool
        ):
            err("security.allow_private_urls must be true or false")

    events = cfg.get("events") or {}
    for i, rule in enumerate(events.get("fastpath") or []):
        if not isinstance(rule, dict) or not rule.get("pattern"):
            err(f"events.fastpath[{i}]: pattern is required")
        elif rule.get("action", "slowpath") not in FASTPATH_ACTIONS:
            err(f"events.fastpath[{i}].action must be one of {sorted(FASTPATH_ACTIONS)}")

    return errors, warnings


def main(argv):
    path = argv[1] if len(argv) > 1 else "config/superagent.yaml"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
    except FileNotFoundError:
        print(f"ERROR: config not found: {path}", file=sys.stderr)
        return 2
    except yaml.YAMLError as exc:
        print(f"ERROR: invalid YAML in {path}: {exc}", file=sys.stderr)
        return 2

    errors, warnings = validate(cfg)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    if errors:
        print(f"{path}: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print(f"{path}: OK" + (f" ({len(warnings)} warning(s))" if warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
