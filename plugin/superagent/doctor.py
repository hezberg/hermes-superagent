"""Install doctor: whole-suite health check, in human sentences.

Every check below corresponds to a failure actually observed during
the first live install (2026-10-31 → 11-01). The design rule (see
docs/PRINCIPLES.md #5): an error must arrive as a sentence with the
fix attached — never as a log tail the user has to decode. So each
check returns {level, text, fix?} with level in ok|warn|error, and
the CLI prints them as prose.

Field failures encoded here:
  1. The API-key env var was set nowhere the gateway could see, so
     every model call went out with a placeholder key.
  2. Toolsets written under `agent.toolsets`, a key Hermes ignores —
     the Router silently got the full default toolset and no kanban.
  3. Clash/mihomo fake-IP DNS: public names resolve into
     198.18.0.0/15, Hermes' SSRF guard calls that "internal", and
     every web fetch is blocked unless the profile allows private
     URLs. Compounded by: profiles do not inherit the default
     profile's security setting.
  4. Rendered configs hand-edited in a rich-text editor arrived with
     curly quotes, and every quoted value was silently wrong.

Pure functions over plain data; the plugin gathers the data.
"""
import ipaddress

EXECUTION_TOOLSETS = {"terminal", "file", "web", "browser", "code_execution"}


def _finding(level, text, fix=None):
    f = {"level": level, "text": text}
    if fix:
        f["fix"] = fix
    return f


def check_config_loaded(cfg, router_profile=None, worker_count=0):
    if not cfg:
        return [_finding(
            "error",
            "Suite config not loaded (~/.hermes/superagent/superagent.yaml is missing or unreadable).",
            "Run the installer (bootstrap.sh, or ./install.sh in a checkout) to complete the install; edit only superagent.yaml, never the rendered profile files.",
        )]
    return [_finding(
        "ok",
        f"Config loaded: Router is {router_profile or '?'}, with {worker_count} worker(s).",
    )]


def check_key_env(providers, env_present):
    """env_present: {env var name: bool} — presence only, never values."""
    out = []
    for name, p in (providers or {}).items():
        var = (p or {}).get("api_key_env")
        if not var:
            out.append(_finding(
                "error", f"provider {name} has no api_key_env (it must name an environment variable, not hold the key itself)."))
        elif not env_present.get(var):
            out.append(_finding(
                "error",
                f"Environment variable {var} is in neither the global .env nor any profile .env - the gateway would send requests with a placeholder key and be rejected.",
                f"Put the key in ~/.hermes/.env (one line: {var}=<your key>), then hermes gateway restart.",
            ))
        else:
            out.append(_finding("ok", f"provider {name}: key variable {var} is in place."))
    return out


def check_router_toolsets(profile_name, profile_cfg):
    cfg = profile_cfg or {}
    agent = cfg.get("agent") or {}
    if "toolsets" in agent:
        return [_finding(
            "error",
            f"{profile_name} still has agent.toolsets in its config - Hermes does not read that key, so the toolset restriction is not in effect.",
            "Reinstall with the current version (the template writes platform_toolsets).",
        )]
    cli = ((cfg.get("platform_toolsets") or {}).get("cli")) or []
    if "kanban" not in cli:
        return [_finding(
            "error",
            f"{profile_name}'s cli toolset has no kanban - it cannot create cards.",
            f"hermes -p {profile_name} tools enable kanban, then start a new session.",
        )]
    extra = [t for t in cli if t in EXECUTION_TOOLSETS]
    if extra:
        return [_finding(
            "warn",
            f"{profile_name} carries execution tools ({', '.join(extra)}) - it may bypass the board and do the work itself.",
            "Reinstall with the current version; the rendered Router has kanban + memory + skills only.",
        )]
    return [_finding("ok", f"{profile_name} toolsets are correct: kanban + memory/skills only, no execution tools.")]


def check_worker_profile(profile_name, profile_cfg):
    cfg = profile_cfg or {}
    cli = ((cfg.get("platform_toolsets") or {}).get("cli")) or []
    if not cli:
        return [_finding(
            "warn",
            f"{profile_name} has no platform_toolsets.cli - the dispatcher force-adds kanban for spawned workers, but a directly opened session has no work tools.",
            "Re-run the installer to re-render.",
        )]
    return [_finding("ok", f"{profile_name} toolsets rendered ({', '.join(cli)}).")]


def is_fake_ip(ip):
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network("198.18.0.0/15")
    except ValueError:
        return False


def check_fake_ip(resolved_ips, profiles_allow_private):
    """profiles_allow_private: {profile name: bool}."""
    fake = [ip for ip in (resolved_ips or []) if is_fake_ip(ip)]
    if not fake:
        return []
    lacking = [p for p, ok in (profiles_allow_private or {}).items() if not ok]
    if lacking:
        return [_finding(
            "error",
            f"This machine's DNS is in fake-IP mode (public names resolve to 198.18-range addresses like {fake[0]}); "
            f"Hermes' SSRF guard treats all web fetches as internal and blocks them. These profiles have not opted out: {', '.join(lacking)}.",
            "Set security.allow_private_urls: true in superagent.yaml and reinstall (it is written into every profile; setting it on the default profile alone does not count - profiles do not inherit it).",
        )]
    return [_finding(
        "ok", "Fake-IP DNS detected, and every profile allows private URLs - web fetches will not be blocked by the SSRF guard.")]


def check_private_base_url(providers):
    out = []
    for name, p in (providers or {}).items():
        url = (p or {}).get("base_url") or ""
        host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            continue
        if not ip.is_global:
            out.append(_finding(
                "warn",
                f"provider {name}'s endpoint is on a non-public address ({host}) - model calls do not pass the SSRF guard, so this is allowed; just make sure this machine can reach it directly (e.g. it is on the same tailnet).",
            ))
    return out


def check_smart_quotes(profile_texts):
    out = []
    for profile, text in (profile_texts or {}).items():
        if text and ("“" in text or "”" in text):
            out.append(_finding(
                "error",
                f"{profile}'s config.yaml contains curly (full-width) quotes - likely edited in a rich-text editor; every quoted value will be read wrong.",
                "Never hand-edit rendered files; edit superagent.yaml (with nano / VS Code) and re-run the installer.",
            ))
    return out


def check_plugin_enablement(enabled, disabled, plugin_present=True):
    """Hermes plugins are opt-in: the loader silently skips any plugin
    whose key is not in plugins.enabled (and plugins.disabled wins).
    `enabled` is None when the config has no plugins.enabled list at
    all (a fresh install may grandfather user plugins on migration,
    but a plugin installed afterwards is not covered)."""
    if not plugin_present:
        return [_finding(
            "error",
            "The plugin directory is missing (~/.hermes/plugins/superagent) - the suite is not fully installed.",
            "Re-run the installer (bootstrap.sh, or ./install.sh in a checkout).",
        )]
    disabled = disabled or []
    if "superagent" in disabled:
        return [_finding(
            "error",
            "superagent is listed in plugins.disabled - the disable list wins over the enable list, so the plugin will not load.",
            "Run hermes plugins enable superagent (it reconciles both lists), then restart the gateway.",
        )]
    if enabled is not None and "superagent" not in enabled:
        return [_finding(
            "error",
            "superagent is not in plugins.enabled - Hermes plugins are opt-in: the directory alone does not load (this is exactly why the status command did not exist on the first live install).",
            "Run hermes plugins enable superagent, then restart the gateway.",
        )]
    if enabled is None:
        return [_finding(
            "warn",
            "The config has no plugins.enabled list yet - a freshly installed plugin may not be registered.",
            "Run hermes plugins enable superagent once to be sure, then restart the gateway.",
        )]
    return [_finding("ok", "The plugin is listed in plugins.enabled and will load.")]


def check_install_drift(manifest_version, running_version, config_mtime, installed_epoch):
    """Catch the two half-updated states: the suite config edited after
    the last install (rendered profiles are stale), and plugin files
    newer than the install record (an interrupted upgrade)."""
    out = []
    if manifest_version and running_version and manifest_version != running_version:
        out.append(_finding(
            "warn",
            f"Plugin version ({running_version}) and the install record ({manifest_version}) disagree - an upgrade may have stopped halfway.",
            "Re-run the installer so every part is on one version.",
        ))
    if config_mtime and installed_epoch and config_mtime > installed_epoch + 1:
        out.append(_finding(
            "warn",
            "superagent.yaml was edited after the last install - the changes are not rendered into the profiles yet; the old config is still in effect.",
            "Re-run the installer to apply the changes.",
        ))
    return out


def check_board(counts):
    if counts is None:
        return [_finding(
            "warn",
            "The board is not initialized yet (no kanban.db) - it is created with the first card, or run hermes kanban init.",
        )]
    total = sum(counts.values())
    return [_finding("ok", f"The board exists: {total} card(s): " +
                     ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))]


def summarize(findings):
    errors = sum(1 for f in findings if f["level"] == "error")
    warns = sum(1 for f in findings if f["level"] == "warn")
    if errors:
        return f"Bottom line: {errors} problem(s) to fix (plus {warns} note(s))."
    if warns:
        return f"Bottom line: no hard problems; {warns} note(s) worth a look."
    return "Bottom line: all clear."
