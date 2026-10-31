#!/usr/bin/env python3
"""Render Hermes profile configs from superagent.yaml.

For the router and each worker, take the matching template under
profiles/ and substitute provider/model values, writing one directory per
profile into the output directory (normally $HERMES_HOME/profiles).

ALL mapping between superagent's provider abstraction and Hermes' own
config keys lives in provider_block() below — if a future Hermes version
changes its config schema, that is the one place to fix.

Usage:
  render_profiles.py --config config/superagent.yaml \
                     --templates profiles --out /path/to/profiles
"""
import argparse
import os
import sys

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required (it ships with Hermes itself).", file=sys.stderr)
    sys.exit(2)

# superagent provider type -> Hermes `model.provider` value.
# "openai-compatible" endpoints are served through Hermes' custom-endpoint
# support; "anthropic" uses the native Anthropic provider with a base_url
# override. See docs/ASSUMPTIONS.md — verify against your Hermes version.
HERMES_PROVIDER = {
    "openai-compatible": "custom",
    "anthropic": "anthropic",
}


def provider_block(provider_cfg):
    """Return the dict of Hermes config values for one provider."""
    ptype = provider_cfg.get("type")
    return {
        "HERMES_PROVIDER": HERMES_PROVIDER.get(ptype, "custom"),
        "BASE_URL": provider_cfg.get("base_url") or "",
        "API_KEY_ENV": provider_cfg.get("api_key_env") or "",
        "PROVIDER_TYPE": ptype or "",
    }


def render_template(text, values):
    out = text
    for key, val in values.items():
        out = out.replace("{{%s}}" % key, str(val))
    return out


def toolsets_yaml(toolsets):
    return "[" + ", ".join(toolsets or []) + "]"


def render_all(cfg, templates_dir, out_dir):
    """Render every profile. Returns the list of profile dirs written."""
    providers = cfg.get("providers") or {}
    written = []

    jobs = [("router", cfg.get("router") or {}, "router")]
    for w in cfg.get("workers") or []:
        jobs.append((w.get("name", "worker"), w, os.path.join("workers", w.get("name", "worker"))))

    for _name, role, template_rel in jobs:
        profile = role.get("profile")
        if not profile:
            continue
        template_path = os.path.join(templates_dir, template_rel, "config.yaml.tmpl")
        with open(template_path, "r", encoding="utf-8") as fh:
            template = fh.read()
        provider_cfg = providers.get(role.get("provider")) or {}
        values = provider_block(provider_cfg)
        values.update(
            {
                "PROFILE_NAME": profile,
                "MODEL": role.get("model") or "",
                "ROLE": role.get("role", ""),
                "TOOLSETS": toolsets_yaml(role.get("toolsets")),
            }
        )
        dest_dir = os.path.join(out_dir, profile)
        os.makedirs(dest_dir, exist_ok=True)
        with open(os.path.join(dest_dir, "config.yaml"), "w", encoding="utf-8") as fh:
            fh.write(render_template(template, values))
        written.append(dest_dir)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--templates", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    with open(args.config, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    written = render_all(cfg, args.templates, args.out)
    for path in written:
        print(f"rendered: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
