"""Inherit the default Hermes profile's model setup.

Design rule (operator's, 2026-11-01): nobody should have to
re-declare a provider they already configured. Any suite role left
without a model inherits the default profile's `model:` block —
provider string included, verbatim — because Hermes knows provider
types the suite's own abstraction does not. The suite config is an
override file, not a parallel universe.
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
    path = os.path.join(home, "config.yaml")
    if not os.path.isfile(path):
        return {}
    try:
        cfg = load_file(path) or {}
    except Exception:
        return {}
    model = cfg.get("model") or {}
    return model if isinstance(model, dict) else {}


def block_model_name(block):
    return (block or {}).get("default") or (block or {}).get("model") or ""


def key_env_of(block):
    return (block or {}).get("api_key_env") or (block or {}).get("key_env") or ""


def inheritance_available(home):
    return bool(block_model_name(default_model_block(home)))


def apply_inheritance(cfg, block):
    """Fill model-less roles from the default profile's model block.

    Returns (effective_cfg, [profile names that inherited]). Roles
    with an explicit model are untouched. The inherited provider is
    a verbatim entry: the renderer copies the block's own provider
    string, base_url, and key variable.
    """
    eff = copy.deepcopy(cfg or {})
    if not block_model_name(block):
        return eff, []
    providers = eff.setdefault("providers", {})
    providers[INHERITED] = {
        "type": "__verbatim__",
        "model_block": dict(block),
        "api_key_env": key_env_of(block),
    }
    inherited = []
    roles = [eff.get("router") or {}] + list(eff.get("workers") or [])
    for role in roles:
        if isinstance(role, dict) and role.get("profile") and not role.get("model"):
            role["provider"] = INHERITED
            role["model"] = block_model_name(block)
            inherited.append(role["profile"])
    return eff, inherited


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
