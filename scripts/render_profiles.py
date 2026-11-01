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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import yaml

    _load = yaml.safe_load
except ImportError:
    # No PyYAML in this interpreter (e.g. Hermes' bundled python):
    # the bundled subset parser covers the suite's config grammar.
    import miniyaml

    _load = miniyaml.parse

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
    provider_cfg = provider_cfg or {}
    if provider_cfg.get("type") == "__verbatim__":
        # Resolved against the default profile's own config: the
        # model block is emitted whole (Hermes owns its shape — the
        # old field-picking dropped keys it did not know), and any
        # named-endpoint sections travel with the profile.
        block = provider_cfg.get("model_block") or {}
        return {
            "HERMES_PROVIDER": block.get("provider") or "custom",
            "BASE_URL": block.get("base_url") or "",
            "API_KEY_ENV": block.get("api_key_env") or block.get("key_env") or "",
            "PROVIDER_TYPE": "__verbatim__",
            "MODEL_BLOCK": block,
            "SECTIONS": provider_cfg.get("sections") or {},
        }
    ptype = provider_cfg.get("type")
    return {
        "HERMES_PROVIDER": HERMES_PROVIDER.get(ptype, "custom"),
        "BASE_URL": provider_cfg.get("base_url") or "",
        "API_KEY_ENV": provider_cfg.get("api_key_env") or "",
        "PROVIDER_TYPE": ptype or "",
        "MODEL_BLOCK": None,
        "SECTIONS": {},
    }


def model_section(values, role):
    """The profile's `model:` section as YAML text.

    Verbatim resolutions emit the resolved block whole, with the
    role's reasoning effort merged in; legacy suite providers keep
    the fixed-shape block the templates have always produced.
    """
    import inherit

    block = values.get("MODEL_BLOCK")
    if block is not None:
        merged = dict(block)
        effort = role.get("reasoning_effort")
        if effort and "reasoning_effort" not in merged:
            merged["reasoning_effort"] = effort
        text = inherit.dump_simple_yaml({"model": merged})
        return text.rstrip("\n")
    lines = [
        "model:",
        f'  provider: "{values["HERMES_PROVIDER"]}"',
        f'  default: "{role.get("model") or ""}"',
        f'  base_url: "{values["BASE_URL"]}"',
        f'  api_key_env: "{values["API_KEY_ENV"]}"',
        f'  reasoning_effort: "{role.get("reasoning_effort") or ""}"',
    ]
    return "\n".join(lines)


def extra_sections(values):
    """Top-level sections a resolution carries (named endpoints)."""
    sections = values.get("SECTIONS") or {}
    if not sections:
        return ""
    import inherit

    return "\n" + inherit.dump_simple_yaml(sections).rstrip("\n")


def render_template(text, values):
    out = text
    for key, val in values.items():
        out = out.replace("{{%s}}" % key, str(val))
    return out


def toolsets_yaml(toolsets):
    return "[" + ", ".join(toolsets or []) + "]"


# Every worker also gets memory + skills on its CLI platform selection:
# without `skills` it cannot load its bundled worker skill, and without
# `memory` it cannot persist anything across sessions. The kanban
# lifecycle toolset is NOT listed here — the Hermes dispatcher force-adds
# it to spawned task workers via the HERMES_KANBAN_TASK environment flag.
WORKER_BASE_TOOLSETS = ("memory", "skills")


def worker_toolsets(role_toolsets):
    out = list(role_toolsets or [])
    for extra in WORKER_BASE_TOOLSETS:
        if extra not in out:
            out.append(extra)
    return out


def security_block(cfg):
    """Hermes `security:` section for a profile config, or "".

    Only rendered when the user opted in (security.allow_private_urls:
    true). Profiles do NOT inherit the default profile's security
    settings — field-verified 2026-11-01: a global
    `hermes config set security.allow_private_urls true` left every
    worker profile still blocked by the SSRF guard — so the suite
    writes the setting into each profile it manages. When the option
    is off the section is omitted entirely, preserving any per-profile
    choice the user made by hand.
    """
    security = cfg.get("security") or {}
    if security.get("allow_private_urls") is True:
        return "security:\n  allow_private_urls: true"
    return ""


def top_level_sections(text):
    """[(key-or-None, section_text)] split at column-0 `key:` lines.

    A preamble (comments/blank lines before the first key) comes back
    with key None. Text-level on purpose: the renderer's consumers
    (installer, doctor) cannot assume a YAML library.
    """
    sections = []
    key, buf = None, []
    for line in (text or "").splitlines(keepends=True):
        stripped = line.rstrip("\n")
        is_key = (
            stripped
            and not stripped[0].isspace()
            and not stripped.startswith("#")
            and ":" in stripped
            and not stripped.startswith("-")
        )
        if is_key:
            if buf:
                sections.append((key, "".join(buf)))
            key, buf = stripped.split(":", 1)[0].strip(), [line]
        else:
            buf.append(line)
    if buf:
        sections.append((key, "".join(buf)))
    return sections


def merge_preserving_sections(rendered, existing,
                              owned_extra=("model", "platform_toolsets", "security", "skills")):
    """Rendered content wins; top-level sections that exist ONLY in
    the on-disk file are carried over.

    A profile's config.yaml is co-owned: the suite renders its keys,
    but Hermes' own setup flows (gateway platform credentials,
    operator tweaks) write others into the same file. Overwriting
    the whole file would delete a wired-up messaging platform on
    the next reconcile — the merge is what lets both owners win.
    Sections the suite OWNS are never preserved from disk, even
    when this render omits them (e.g. the security block vanishing
    is exactly how an operator turns it off).
    """
    if not existing:
        return rendered
    owned = {k for k, _ in top_level_sections(rendered) if k} | set(owned_extra)
    extra = [t for k, t in top_level_sections(existing)
             if k and k not in owned]
    if not extra:
        return rendered
    out = rendered if rendered.endswith("\n") else rendered + "\n"
    for section in extra:
        out += section if section.endswith("\n") else section + "\n"
    return out


def render_all(cfg, templates_dir, out_dir):
    """Render every profile. Returns the list of profile dirs written."""
    providers = cfg.get("providers") or {}
    written = []

    def template_for(template_rel, fallback_rel=None):
        path = os.path.join(templates_dir, template_rel, "config.yaml.tmpl")
        if fallback_rel and not os.path.isfile(path):
            path = os.path.join(templates_dir, fallback_rel, "config.yaml.tmpl")
        return path

    jobs = [("router", cfg.get("router") or {}, "router", None, False)]
    for w in cfg.get("workers") or []:
        # Workers share ONE template (they differed only in config
        # values all along); a per-name template may still override.
        jobs.append((w.get("name", "worker"), w,
                     os.path.join("workers", w.get("name", "worker")), "worker", True))

    for _name, role, template_rel, fallback_rel, is_worker in jobs:
        profile = role.get("profile")
        if not profile:
            continue
        template_path = template_for(template_rel, fallback_rel)
        with open(template_path, "r", encoding="utf-8") as fh:
            template = fh.read()
        provider_cfg = providers.get(role.get("provider")) or {}
        values = provider_block(provider_cfg)
        values.update(
            {
                "PROFILE_NAME": profile,
                "MODEL_SECTION": model_section(values, role),
                "EXTRA_SECTIONS": extra_sections(values),
                "REASONING_EFFORT": role.get("reasoning_effort") or "",
                "ROLE": role.get("role", ""),
                "TOOLSETS": toolsets_yaml(
                    worker_toolsets(role.get("toolsets")) if is_worker else role.get("toolsets")
                ),
                "SECURITY_BLOCK": security_block(cfg),
            }
        )
        dest_dir = os.path.join(out_dir, profile)
        os.makedirs(dest_dir, exist_ok=True)
        with open(os.path.join(dest_dir, "config.yaml"), "w", encoding="utf-8") as fh:
            fh.write(render_template(template, values))
        # SOUL.md is the profile's identity slot — Hermes loads it
        # from the profile's own home into every session. This is
        # where the role's default behavior lives (a skill is only a
        # reference the model may consult; the SOUL is always on).
        soul_src = os.path.join(templates_dir, template_rel, "SOUL.md")
        if fallback_rel and not os.path.isfile(soul_src):
            soul_src = os.path.join(templates_dir, fallback_rel, "SOUL.md")
        if os.path.isfile(soul_src):
            with open(soul_src, "r", encoding="utf-8") as fh:
                soul = fh.read()
            with open(os.path.join(dest_dir, "SOUL.md"), "w", encoding="utf-8") as fh:
                fh.write(render_template(soul, values))
        written.append(dest_dir)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--templates", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    with open(args.config, "r", encoding="utf-8") as fh:
        cfg = _load(fh.read())
    written = render_all(cfg, args.templates, args.out)
    for path in written:
        print(f"rendered: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
