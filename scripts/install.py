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


def repo_url():
    """The clone's origin URL, for state.json; canonical fallback."""
    try:
        result = subprocess.run(
            ["git", "-C", REPO, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
        )
        url = (result.stdout or "").strip()
        if url:
            return url
    except Exception:
        pass
    return "https://github.com/hezberg/hermes-superagent.git"


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
        if isinstance(role, dict) and (role.get("model") or role.get("provider")):
            return False
    return True


def _inheritance_available(home):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import inherit as inherit_mod

    return inherit_mod.inheritance_available(home)


def _clean_env_line(line):
    """Normalize one raw .env line for parsing: BOM / zero-width
    characters and a full-width equals sign (a classic IME slip)
    must not make a present key read as missing."""
    return (line.replace("\ufeff", "").replace("\u200b", "")
            .replace("\uff1d", "="))


def _read_env_file(path):
    values = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = _clean_env_line(line.strip())
                if line.startswith("export "):
                    line = line[len("export "):].lstrip()
                if line and not line.startswith("#") and "=" in line:
                    name, value = line.split("=", 1)
                    value = value.strip()
                    if len(value) >= 2 and value[0] == value[-1] \
                            and value[0] in "\"'":
                        value = value[1:-1]
                    values[name.strip()] = value
    except OSError:
        pass
    return values


def key_diagnosis(home, var):
    """Why a key variable reads as missing, in one sentence.

    The installer must diagnose, not assert: "put the key in .env"
    is a false instruction when the operator already did and the
    line is empty, malformed, or in another file. Names and shapes
    only — never the value.
    """
    path = os.path.join(home, ".env")
    try:
        with open(path, encoding="utf-8") as fh:
            raw_lines = fh.read().splitlines()
    except OSError:
        return f"~/.hermes/.env does not exist yet — create it with one line: {var}=<your key>"
    mentions = [ln for ln in raw_lines if var in ln and not ln.strip().startswith("#")]
    if not mentions:
        similar = [ln.split("=")[0].strip() for ln in raw_lines
                   if "=" in ln and var.split("_")[0].lower()
                   in ln.split("=")[0].strip().lower()]
        hint = f" (a similar name exists: {similar[0]} — typo?)" if similar else ""
        return f"no line for {var} exists in ~/.hermes/.env{hint} — add one line: {var}=<your key>"
    line = _clean_env_line(mentions[-1].strip())
    body = line[len("export "):].lstrip() if line.startswith("export ") else line
    if "=" not in body:
        return f"a line mentions {var} in ~/.hermes/.env but has no '=' and no value — make it {var}=<your key>"
    name, value = body.split("=", 1)
    if name.strip() != var:
        return (f"~/.hermes/.env has a line named '{name.strip()}' — close to, but not, "
                f"{var}; rename it to {var}")
    if not value.strip():
        return (f"{var} IS in ~/.hermes/.env but its value is empty — the line has "
                "nothing after '='. Put the key there; everything else is automatic.")
    return f"{var} is present in ~/.hermes/.env (the parser still could not use it — check the line's shape)"


def _value_sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_env_value(path, var, value):
    lines = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    out = [ln for ln in lines if not ln.startswith(var + "=")]
    out.append(f"{var}={value}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    os.chmod(path, 0o600)


def sync_profile_keys(home, eff_cfg, dry_run, changes, synced=None):
    """Converge each profile's provider key onto the global .env.

    Single source of truth: ~/.hermes/.env. The suite chose the key
    variable names it rendered into these profiles' configs, so for
    those variables the global value IS the value — a profile copy
    that differs is a stale copy, not a preference, and it follows
    the global one. (An earlier fill-gaps-only rule protected a
    hypothetical per-profile key at the cost of the operator's real
    workflow: rotate the key in the global file and have it take
    effect. The operator's verdict, 2026-11-01: no global thinking.
    A per-profile key, if ever wanted, belongs in the suite config
    as an explicit feature — not in a hand-edited .env.)

    Values are never printed and never leave the box; files are
    0600. Returns (missing_vars, baseline): variables with no value
    in the global file or the process environment (the operator's
    one remaining job: put them in ~/.hermes/.env), and a
    {profile: {var: sha256}} baseline for state.json, so the plugin
    can later tell "global rotated, profiles not yet converged"
    apart from "everything in step" without seeing any value.
    """
    providers = eff_cfg.get("providers") or {}
    roles = [eff_cfg.get("router") or {}] + list(eff_cfg.get("workers") or [])
    wanted = {}
    for role in roles:
        if not isinstance(role, dict):
            continue
        var = (providers.get(role.get("provider")) or {}).get("api_key_env")
        if role.get("profile") and var:
            wanted[role["profile"]] = var
    baseline = {p: dict(v) for p, v in (synced or {}).items()}
    if not wanted:
        return [], baseline
    global_env = _read_env_file(os.path.join(home, ".env"))
    missing = []
    for profile, var in sorted(wanted.items()):
        path = os.path.join(home, "profiles", profile, ".env")
        value = global_env.get(var) or os.environ.get(var)
        if not value:
            if var not in missing:
                missing.append(var)
            continue  # nothing to converge onto; profile left as-is
        current = _read_env_file(path).get(var)
        if current != value:
            if not dry_run:
                _write_env_value(path, var, value)
            changes.append(f"key sync ({profile})" if not current
                           else f"key sync ({profile}: updated)")
        baseline.setdefault(profile, {})[var] = _value_sha(value)
    return missing, baseline


def load_yaml(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        import yaml

        return yaml.safe_load(text)
    except ImportError:
        # The installer can be launched by interpreters with no
        # PyYAML (Hermes' bundled python is one — it killed real
        # upgrades). The bundled subset parser covers the config.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import miniyaml

        return miniyaml.parse(text)


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


def _is_protected_rel(rel):
    """Operator/Hermes property inside a profile dir — never managed,
    snapshotted, rolled back, or uninstalled by the suite."""
    parts = rel.replace(os.sep, "/").split("/")
    return parts[-1] == ".env" or parts[0] in ("sessions", "logs", "memory")


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
    if not profiles:
        # Legacy manifests carry no profile list; recover the profile
        # names from their created_paths instead.
        for path in paths:
            if os.path.basename(os.path.dirname(path)) == "profiles":
                profiles.append(os.path.basename(path))
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
    # Profiles: snapshot only the suite-managed files. A profile dir
    # also holds the operator's .env and Hermes' sessions/logs; a
    # rollback restores renders, it does not rewind a living profile.
    recorded = (state or {}).get("files") or {}
    for profile in profiles:
        base = os.path.join(home, "profiles", profile)
        managed = recorded.get(f"profile:{profile}") or {}
        rels = [r for r in managed if not _is_protected_rel(r)]
        if not rels and os.path.isdir(base):
            # Legacy state recorded nothing usable: take the rendered
            # files only, still skipping protected entries.
            rels = [r for r in tree_hashes(base, skip_topdirs=("skills",))
                    if not _is_protected_rel(r)]
        for rel in rels:
            src_f = os.path.join(base, rel)
            if not os.path.isfile(src_f):
                continue
            dst_f = os.path.join(prev, "profiles", profile, rel)
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            shutil.copy2(src_f, dst_f)
            manifest["paths"].append(os.path.join("profiles", profile, rel))
    with open(os.path.join(prev, "prev.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
    return manifest["version"]


def do_rollback(home):
    prev = os.path.join(home, "superagent", "prev")
    meta_path = os.path.join(prev, "prev.json")
    if not os.path.isfile(meta_path):
        say("No previous-generation snapshot to roll back to (one is created by the first successful upgrade).")
        return EXIT_FAIL
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    for rel in meta.get("paths", []):
        src = os.path.join(prev, rel)
        dst = os.path.join(home, rel)
        if rel.replace(os.sep, "/").startswith("profiles/"):
            # Profile entries in the snapshot are individual managed
            # files; copy each back, never replace the living dir.
            if os.path.isfile(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
        elif os.path.isdir(src):
            replace_tree(src, dst)
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
    say(f"Rolled back to the previous generation (version {meta.get('version') or 'unknown'}). "
        "Restart the gateway to apply: hermes gateway restart")
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
            if _inheritance_available(home):
                say("note: superagent.yaml is still the empty template, but your default "
                    "Hermes profile already has a model - the suite will inherit it. "
                    "Fill in superagent.yaml only to override a role's model.")
                return suite_cfg, cfg, EXIT_OK
            # A pristine suite file is a leftover phase-one template.
            # A filled --config reseeds it; otherwise, stop politely.
            if explicit and os.path.isfile(explicit):
                seeded = load_yaml(explicit)
                if not is_pristine(seeded):
                    if not dry_run:
                        shutil.copy2(explicit, suite_cfg)
                    say("Replaced the empty template with the config given via --config.")
                    return suite_cfg, seeded, EXIT_OK
            say("Config not filled in yet: ~/.hermes/superagent/superagent.yaml has no "
                "provider or model selections. Fill it in and re-run the same command.")
            return None, None, EXIT_NEEDS_CONFIG
        if explicit and os.path.abspath(explicit) != os.path.abspath(suite_cfg):
            say("note: an active config already exists at ~/.hermes/superagent/superagent.yaml "
                "and wins (--config only seeds the first install).")
        return suite_cfg, cfg, EXIT_OK

    if explicit:
        if not os.path.isfile(explicit):
            say(f"ERROR: --config file not found: {explicit}")
            return None, None, EXIT_PREFLIGHT
        cfg = load_yaml(explicit)
        if is_pristine(cfg):
            say("That --config is still the empty template - select a provider or model first, or rely on your default Hermes profile.")
            return None, None, EXIT_NEEDS_CONFIG
        if not dry_run:
            os.makedirs(suite_dir, exist_ok=True)
            shutil.copy2(explicit, suite_cfg)
        say(f"Seeded the config to {suite_cfg} - from now on, edit that file only.")
        return suite_cfg, cfg, EXIT_OK

    template = os.path.join(REPO, "config", "superagent.yaml")
    if not dry_run:
        os.makedirs(suite_dir, exist_ok=True)
        shutil.copy2(template, suite_cfg)
    say("First install: generating your config file:")
    say(f"  {suite_cfg}")
    if _inheritance_available(home):
        say("Your default Hermes profile already has a model, so there is nothing "
            "you must fill in - the suite inherits it. Edit superagent.yaml only "
            "to override a role's model, and re-run to apply.")
        return suite_cfg, load_yaml(suite_cfg), EXIT_OK
    say("Fill in each provider's base_url and each role's model (the file explains "
        "itself), then re-run the same command. None of your config lives in the repo "
        "tree, so git pull can never conflict with it.")
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
    parser.add_argument("--wizard", action="store_true",
                        help="Run the interactive setup wizard instead of a bare install")
    parser.add_argument("--home", default=None,
                        help="Hermes home (default: $HERMES_HOME or ~/.hermes)")
    args = parser.parse_args(argv)

    home = args.home or os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    version = repo_version()

    if args.wizard:
        sys.path.insert(0, os.path.join(REPO, "plugin"))
        os.environ["HERMES_HOME"] = home
        try:
            from superagent.wizard import run_wizard

            return run_wizard(home, REPO)
        except ImportError as exc:
            say(f"ERROR: the setup wizard could not load ({exc}).")
            return EXIT_FAIL

    if args.rollback:
        return do_rollback(home)

    # ------------------------------------------------------------ preflight
    if not os.path.isdir(home):
        say(f"ERROR: Hermes home does not exist ({home}). Run Hermes once first.")
        return EXIT_PREFLIGHT
    if shutil.which("hermes") is None and not args.dry_run:
        say("ERROR: 'hermes' CLI not found. This suite is an add-on to Hermes, not a bundle.")
        return EXIT_PREFLIGHT
    suite_cfg, cfg, code = resolve_config(home, args.config, args.dry_run)
    if suite_cfg is None:
        return code

    # ------------------------------------------------- resolution
    # Roles SELECT providers/models that already exist in the
    # default Hermes profile's config; the suite declares none of
    # its own. The effective config is what gets validated,
    # rendered, and key-synced; the file on disk stays the
    # operator's selections.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import inherit as inherit_mod

    default_cfg = inherit_mod.default_config(home)
    eff_cfg, res_notes, res_errors = inherit_mod.apply_resolution(cfg, default_cfg)
    if res_errors:
        say("Config resolution failed - these selections do not exist in your Hermes config:")
        for err in res_errors:
            say(f"ERROR: {err}")
        return EXIT_FAIL
    inherited_roles = [n["profile"] for n in res_notes if n["via"] == "inherited"]
    if inherited_roles:
        model_block = inherit_mod.default_model_block(home)
        say("Inheriting the default profile's model for "
            + ", ".join(inherited_roles)
            + f" ({model_block.get('provider') or 'custom'} / "
            + f"{inherit_mod.block_model_name(model_block)}).")
    for note in res_notes:
        if note["via"] == "selection":
            say(f"Selected for {note['profile']}: {note['detail']} (from your Hermes config).")

    # ------------------------------------------------------------ validate
    import validate_config as validate_mod

    errors, _warnings = validate_mod.validate(eff_cfg)
    if errors:
        say("Config validation failed - fix these (all in ~/.hermes/superagent/superagent.yaml):")
        for err in errors:
            say(f"ERROR: {err}")
        return EXIT_FAIL

    router = (eff_cfg.get("router") or {}).get("profile")
    workers = [w.get("profile") for w in eff_cfg.get("workers") or []]
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

    def converge_files(src_dir, dst, label, skip_topdirs=()):
        """Per-file convergence for LIVING directories (profiles).

        A profile directory is not a render artifact: Hermes and the
        operator keep their own files there — .env holding the API
        key, sessions, logs, memory. Whole-tree replacement (the old
        behaviour) deleted the profiles' .env on every config change;
        the profile then failed every model request while the global
        .env masked the loss in checks (field failure, 2026-11-01).
        The suite manages only the files it renders and leaves
        everything else in the directory untouched.
        """
        staged = tree_hashes(src_dir, skip_topdirs=skip_topdirs)
        changed = False
        render_mod = None
        for rel, digest in staged.items():
            target = os.path.join(dst, rel)
            current_bytes = None
            if os.path.isfile(target):
                with open(target, "rb") as fh:
                    current_bytes = fh.read()
            with open(os.path.join(src_dir, rel), "rb") as fh:
                data = fh.read()
            if rel == "config.yaml" and current_bytes is not None:
                # A profile's config.yaml is co-owned: Hermes' setup
                # flows write their own top-level sections into it
                # (messaging platform credentials, operator tweaks).
                # The render owns only its keys; sections it does not
                # know are preserved (see render_profiles).
                if render_mod is None:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(
                        "sa_render_profiles",
                        os.path.join(REPO, "scripts", "render_profiles.py"))
                    render_mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(render_mod)
                data = render_mod.merge_preserving_sections(
                    data.decode("utf-8"), current_bytes.decode("utf-8")
                ).encode("utf-8")
                digest = hashlib.sha256(data).hexdigest()
            current = (hashlib.sha256(current_bytes).hexdigest()
                       if current_bytes is not None else None)
            if current != digest:
                changed = True
                if not args.dry_run:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, "wb") as fh:
                        fh.write(data)
        if changed:
            changes.append(label)
            return "updated"
        return "unchanged"

    # ------------------------------------------------------------ resources
    plugin_src = os.path.join(REPO, "plugin", "superagent")
    plugin_dst = os.path.join(home, "plugins", "superagent")
    with tempfile.TemporaryDirectory() as tmp:
        staged_plugin = os.path.join(tmp, "plugin")
        shutil.copytree(plugin_src, staged_plugin,
                        ignore=shutil.ignore_patterns("__pycache__"))
        stamp_version(staged_plugin, version)
        plugin_status = converge_tree(staged_plugin, plugin_dst, "plugin")

        rendered = os.path.join(tmp, "profiles")
        eff_path = os.path.join(tmp, "effective.yaml")
        with open(eff_path, "w", encoding="utf-8") as fh:
            fh.write(inherit_mod.dump_simple_yaml(eff_cfg))
        r = subprocess.run(
            [sys.executable, os.path.join(REPO, "scripts", "render_profiles.py"),
             "--config", eff_path, "--templates", os.path.join(REPO, "profiles"),
             "--out", rendered],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            say("Profile rendering failed:")
            say((r.stdout or "") + (r.stderr or ""))
            return EXIT_FAIL
        profile_status = {}
        managed_profile_files = {}
        for profile in profiles:
            profile_status[profile] = converge_files(
                os.path.join(rendered, profile),
                os.path.join(home, "profiles", profile),
                f"profile {profile}",
                skip_topdirs=("skills",),
            )
            managed_profile_files[profile] = tree_hashes(
                os.path.join(rendered, profile), skip_topdirs=("skills",))

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

    # Memory seeds: each profile's built-in memory is the agent's
    # own notebook (Hermes loads memories/MEMORY.md from the profile
    # home). The suite plants a starting page — role facts the agent
    # would otherwise learn slowly — ONCE. After that the file
    # belongs to the agent: never overwritten, never recorded as
    # managed, left behind by uninstall like .env and sessions.
    role_by_profile = {router: "router"}
    for w in (eff_cfg.get("workers") or []):
        role_by_profile[w.get("profile")] = w.get("role") or w.get("name") or "worker"
    for profile, kind in skill_map:
        if not profile:
            continue
        seed_src = os.path.join(REPO, "profiles", kind, "memory-seed.md")
        seed_dst = os.path.join(home, "profiles", profile, "memories", "MEMORY.md")
        if os.path.exists(seed_dst) or not os.path.isfile(seed_src):
            continue
        with open(seed_src, encoding="utf-8") as fh:
            seed = fh.read()
        seed = seed.replace("{{PROFILE_NAME}}", profile).replace(
            "{{ROLE}}", role_by_profile.get(profile, kind))
        if not args.dry_run:
            os.makedirs(os.path.dirname(seed_dst), exist_ok=True)
            with open(seed_dst, "w", encoding="utf-8") as fh:
                fh.write(seed)
        changes.append(f"memory seed ({profile})")

    prior_synced = {}
    if os.path.isfile(state_path(home)):
        try:
            with open(state_path(home), encoding="utf-8") as fh:
                prior_synced = json.load(fh).get("synced_keys") or {}
        except Exception:
            prior_synced = {}
    missing_key_vars, synced_keys = sync_profile_keys(
        home, eff_cfg, args.dry_run, changes, synced=prior_synced)

    tick_src = os.path.join(REPO, "scripts", "reminder_tick.py")
    with open(tick_src, encoding="utf-8") as fh:
        tick_bytes = fh.read().replace("__HERMES_HOME__", home).encode("utf-8")
    tick_dst = os.path.join(home, "scripts", "superagent-reminder-tick.py")
    tick_status = converge_file(tick_bytes, tick_dst, "reminder tick script")
    if tick_status == "updated" and not args.dry_run:
        os.chmod(tick_dst, 0o755)

    # ------------------------------------------------------------ ensures
    ensures = []
    ensures.append(("plugin enablement", run_hermes(["plugins", "enable", "superagent"], args.dry_run)))
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
    ensures.append(("reminder cron", cron_present))

    # ------------------------------------------------------------ state
    files = {"plugin": tree_hashes(plugin_dst)}
    kind_by_profile = {router: "router"}
    for w in workers:
        kind_by_profile[w] = "worker"
    for profile in profiles:
        # Only the files the suite renders are recorded as managed.
        # The rest of a profile directory (.env, sessions, logs)
        # belongs to Hermes and the operator; uninstall and rollback
        # must never treat it as suite property.
        managed = dict(managed_profile_files.get(profile, {}))
        kind = kind_by_profile.get(profile)
        if kind:
            skill_rel = f"skills/{kind}-superagent/SKILL.md"
            skill_path = os.path.join(home, "profiles", profile, skill_rel)
            if os.path.isfile(skill_path):
                with open(skill_path, "rb") as fh:
                    managed[skill_rel] = hashlib.sha256(fh.read()).hexdigest()
        files[f"profile:{profile}"] = managed
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
        # Where this install came from, so `hermes superagent upgrade`
        # never has to ask the operator where the checkout lives.
        "source_repo": REPO,
        "repo_url": repo_url(),
        # Hashes (never values) of the keys the sync planted in each
        # profile, so a later global-key rotation can tell a synced
        # copy apart from a profile's own deliberate value.
        "synced_keys": synced_keys,
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
        say(f"Upgraded: {old_version} -> {version}")
    elif old_version:
        say(f"Already at {version}; this run was a convergence check")
    else:
        say(f"Installed: {version}")
    if changes:
        say("Changed: " + ", ".join(changes))
    else:
        say("Changed: nothing (everything already at the desired state)")
    soft = [name for name, ok in ensures if not ok]
    if soft:
        say("These steps did not complete automatically; they do not affect the main chain and can be done by hand later: " + ", ".join(soft))
    if cron_created:
        next_steps.append("Point the reminder cron at a delivery platform: find it in "
                            "hermes cron list, then hermes cron edit <id> --deliver feishu")
    for var in missing_key_vars:
        next_steps.append(key_diagnosis(home, var))
    for step in next_steps:
        say(f"Next step: {step}")
    if missing_key_vars:
        say("The suite is installed, but the Router cannot call a model until the "
            "key above is in place. Once it is, everything else is automatic — "
            "then: hermes gateway restart, and hermes --profile sa-router.")
    else:
        say("Finish with: hermes gateway restart - then give the Router a task.")
    if hard_errors:
        say("")
        say("WARNING: postflight checks found hard problems; the install does not count as complete:")
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
        if "api_key_env" in text or "plugins.enabled" in text or "plugins.disabled" in text or "profile_routes" in text:
            steps.append(f.get("fix") or text)
        else:
            hard.append(text)
    return hard, steps


if __name__ == "__main__":
    sys.exit(main())
