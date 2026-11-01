"""Resolve suite roles against the default Hermes profile's config.

Design rule (operator's, 2026-11-01, stated twice and then in full):
superagent does not maintain its own providers or models. The user
already configured providers and models in Hermes; a suite role
only SELECTS among them — by name — or selects nothing and takes
the default profile's model. Endpoints, base URLs and key variables
are never re-declared in superagent.yaml.

Resolution sources, all inside ~/.hermes/config.yaml:
- the `model:` block (the default selection),
- the `providers:` mapping and the `custom_providers:` list (named
  endpoints the user added in Hermes' own settings).

A selected named endpoint is copied into the rendered profile
config exactly the way Hermes' own profile seeding does it
(hermes_cli/profile_model_seed.py): the model block points at it
(`custom:<name>`) and the entry travels with the profile, because a
bare reference is "Unknown provider" on the first turn.

Legacy: a suite config may still define its own `providers:` (the
pre-0.7 format). Roles pointing at those render exactly as before.
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import yaml

    _load = yaml.safe_load
except ImportError:
    import miniyaml

    _load = miniyaml.parse

INHERITED = "__inherited__"


def load_file(path):
    with open(path, encoding="utf-8") as fh:
        return _load(fh.read())


def default_model_block(home):
    """The `model:` mapping of ~/.hermes/config.yaml, or {}."""
    model = default_config(home).get("model") or {}
    return model if isinstance(model, dict) else {}


def default_config(home):
    """The whole of ~/.hermes/config.yaml (the default profile), or {}."""
    path = os.path.join(home, "config.yaml")
    if not os.path.isfile(path):
        return {}
    try:
        cfg = load_file(path) or {}
    except Exception:
        return {}
    return cfg if isinstance(cfg, dict) else {}


def block_model_name(block):
    return (block or {}).get("default") or (block or {}).get("model") or ""


def key_env_of(block):
    return (block or {}).get("api_key_env") or (block or {}).get("key_env") or ""


def inheritance_available(home):
    return bool(block_model_name(default_model_block(home)))


# ----------------------------------------------------------------------
# The Hermes provider registry: named endpoints the user already
# configured in the default profile's config.yaml.
# ----------------------------------------------------------------------

def _norm_name(name):
    text = str(name or "").strip()
    if text.lower().startswith("custom:"):
        text = text[len("custom:"):]
    return text.strip().lower()


def _entry_key_var(entry):
    return (entry or {}).get("api_key_env") or (entry or {}).get("key_env") or ""


def _entry_model(entry):
    return (entry or {}).get("default") or (entry or {}).get("model") or ""


def provider_registry(default_cfg):
    """Named endpoints from `providers:` / `custom_providers:`.

    Each item: {names (normalized, matchable), ref (the model.provider
    string Hermes expects), section (where the raw entry lives),
    entry (the raw entry, copied verbatim into rendered profiles),
    key_var, model}.
    """
    out = []
    providers = (default_cfg or {}).get("providers")
    if isinstance(providers, dict):
        for key, entry in providers.items():
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or key
            names = {_norm_name(key), _norm_name(name)}
            if entry.get("provider_key"):
                names.add(_norm_name(entry["provider_key"]))
            out.append({
                "names": names, "ref": f"custom:{name}",
                "section": ("providers", key), "entry": entry,
                "key_var": _entry_key_var(entry), "model": _entry_model(entry),
            })
    custom = (default_cfg or {}).get("custom_providers")
    if isinstance(custom, list):
        for entry in custom:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            out.append({
                "names": {_norm_name(entry["name"])},
                "ref": f"custom:{entry['name']}",
                "section": ("custom_providers", None), "entry": entry,
                "key_var": _entry_key_var(entry), "model": _entry_model(entry),
            })
    return out


def find_entry(entries, name):
    wanted = _norm_name(name)
    for entry in entries:
        if wanted in entry["names"]:
            return entry
    return None


def _sections_for(entry):
    if entry is None:
        return {}
    kind, key = entry["section"]
    if kind == "providers":
        return {"providers": {key: copy.deepcopy(entry["entry"])}}
    return {"custom_providers": [copy.deepcopy(entry["entry"])]}


def available_selections(default_cfg, entries):
    """The menu of selectable provider names, for error messages."""
    names = []
    block = (default_cfg or {}).get("model") or {}
    if block.get("provider"):
        names.append(str(block["provider"]))
    names += [e["ref"] for e in entries]
    return names


def _set_resolved(providers, role, key, model_block, key_var, sections):
    providers[key] = {
        "type": "__verbatim__",
        "model_block": model_block,
        "api_key_env": key_var,
        "sections": sections,
    }
    role["provider"] = key
    role["model"] = model_block.get("default") or model_block.get("model") or ""


def apply_resolution(cfg, default_cfg):
    """Resolve every role's selection against the default config.

    Returns (effective_cfg, notes, errors). Each note is
    {profile, via, detail} with via one of "inherited" (the default
    profile's model, untouched), "selection" (a named Hermes
    provider and/or a model override), "legacy" (a provider the
    suite config still defines itself). Errors name the available
    selections — the suite never invents a provider.
    """
    eff = copy.deepcopy(cfg or {})
    default_cfg = default_cfg or {}
    block = default_cfg.get("model") or {}
    if not isinstance(block, dict):
        block = {}
    entries = provider_registry(default_cfg)
    providers = eff.setdefault("providers", {})
    legacy = {
        name for name, p in providers.items()
        if isinstance(p, dict) and p.get("type") != "__verbatim__"
    }
    default_entry = find_entry(entries, block.get("provider")) if block.get("provider") else None
    notes, errors = [], []

    def default_route(role, profile, sel_model):
        """The default profile's model block, optionally re-modelled."""
        if not block_model_name(block):
            return False
        if not sel_model:
            if INHERITED not in providers:
                _set_resolved(providers, role, INHERITED, dict(block),
                              key_env_of(block), _sections_for(default_entry))
            else:
                role["provider"] = INHERITED
                role["model"] = block_model_name(block)
            notes.append({"profile": profile, "via": "inherited",
                          "detail": f"{block.get('provider') or 'custom'} / {block_model_name(block)}"})
        else:
            mb = dict(block)
            mb["default"] = sel_model
            _set_resolved(providers, role, f"__resolved_{profile}__", mb,
                          key_env_of(block), _sections_for(default_entry))
            notes.append({"profile": profile, "via": "selection",
                          "detail": f"{block.get('provider') or 'custom'} / {sel_model}"})
        return True

    roles = [eff.get("router") or {}] + list(eff.get("workers") or [])
    for role in roles:
        if not isinstance(role, dict) or not role.get("profile"):
            continue
        profile = role["profile"]
        sel_provider = str(role.get("provider") or "").strip()
        sel_model = str(role.get("model") or "").strip()
        if sel_provider in legacy and sel_model:
            notes.append({"profile": profile, "via": "legacy",
                          "detail": f"{sel_provider} / {sel_model}"})
            continue
        if sel_provider and sel_provider not in legacy:
            entry = find_entry(entries, sel_provider)
            if entry is not None:
                mb = {"provider": entry["ref"],
                      "default": sel_model or entry["model"] or block_model_name(block)}
                _set_resolved(providers, role, f"__resolved_{profile}__", mb,
                              entry["key_var"], _sections_for(entry))
                notes.append({"profile": profile, "via": "selection",
                              "detail": f"{entry['ref']} / {mb['default']}"})
                continue
            if _norm_name(sel_provider) != _norm_name(block.get("provider")):
                menu = ", ".join(available_selections(default_cfg, entries)) or "(none configured)"
                errors.append(
                    f"{profile}: provider '{sel_provider}' is not in your Hermes config. "
                    f"Available selections: {menu}. Providers live in Hermes — add it "
                    "there first (Settings -> Providers, or hermes setup), then select it here.")
                continue
        # Empty selection, a legacy name with no model, or the default
        # provider named explicitly: the default profile's model.
        if not default_route(role, profile, sel_model):
            if sel_model or (sel_provider and sel_provider not in legacy):
                errors.append(
                    f"{profile}: selects '{sel_provider or sel_model}' but the default "
                    "Hermes profile has no model configured to select from.")
    return eff, notes, errors


def apply_inheritance(cfg, block):
    """Compatibility wrapper: pure default-block inheritance.

    Returns (effective_cfg, [profiles that inherited]).
    """
    eff, notes, _errors = apply_resolution(cfg, {"model": block or {}})
    return eff, [n["profile"] for n in notes if n["via"] == "inherited"]


# ----------------------------------------------------------------------
# A tiny YAML emitter for plain data (the effective config is written
# to a temp file for the render subprocess). Strings are always
# double-quoted; structure is dicts/lists/scalars only.
# ----------------------------------------------------------------------

def _scalar(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _emit_map(mapping, indent, lines):
    pad = " " * indent
    for key, value in mapping.items():
        if isinstance(value, dict) and value:
            lines.append(f"{pad}{key}:")
            _emit_map(value, indent + 2, lines)
        elif isinstance(value, list) and value:
            lines.append(f"{pad}{key}:")
            _emit_list(value, indent + 2, lines)
        elif isinstance(value, dict):
            lines.append(f"{pad}{key}: {{}}")
        elif isinstance(value, list):
            lines.append(f"{pad}{key}: []")
        else:
            lines.append(f"{pad}{key}: {_scalar(value)}")


def _emit_list(items, indent, lines):
    pad = " " * indent
    for item in items:
        if isinstance(item, dict) and item:
            first = True
            for key, value in item.items():
                prefix = f"{pad}- " if first else f"{pad}  "
                first = False
                if isinstance(value, dict) and value:
                    lines.append(f"{prefix}{key}:")
                    _emit_map(value, indent + 4, lines)
                elif isinstance(value, list) and value:
                    lines.append(f"{prefix}{key}:")
                    _emit_list(value, indent + 4, lines)
                elif isinstance(value, dict):
                    lines.append(f"{prefix}{key}: {{}}")
                elif isinstance(value, list):
                    lines.append(f"{prefix}{key}: []")
                else:
                    lines.append(f"{prefix}{key}: {_scalar(value)}")
        elif isinstance(item, list) and item:
            lines.append(f"{pad}-")
            _emit_list(item, indent + 2, lines)
        elif isinstance(item, dict):
            lines.append(f"{pad}- {{}}")
        elif isinstance(item, list):
            lines.append(f"{pad}- []")
        else:
            lines.append(f"{pad}- {_scalar(item)}")


def dump_simple_yaml(data):
    lines = []
    if isinstance(data, dict):
        _emit_map(data, 0, lines)
    return "\n".join(lines) + "\n"
