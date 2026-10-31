#!/usr/bin/env bash
# hermes-superagent installer.
#
# Adds the Super-agent layer to an EXISTING Hermes installation:
#   - plugin        -> $HERMES_HOME/plugins/superagent
#   - profiles      -> $HERMES_HOME/profiles/<router + workers> (rendered)
#   - suite config  -> $HERMES_HOME/superagent/superagent.yaml
#   - a manifest    -> $HERMES_HOME/superagent/manifest.json (uninstall
#                      removes exactly what the manifest lists)
#
# It never modifies pre-existing Hermes files. If any target path already
# exists, it aborts unless --force is given (with --force, the previous
# suite-owned copy is backed up under superagent/backups/ first).
#
# Portable across Ubuntu 24.04 and macOS (bash 3.2+; no GNU-only flags).
#
# Usage:
#   ./install.sh [--config path/to/superagent.yaml] [--dry-run] [--force]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
CONFIG="$SCRIPT_DIR/config/superagent.yaml"
DRY_RUN=0
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --force) FORCE=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

say() { printf '%s\n' "$*"; }
run() {
  if [ "$DRY_RUN" = "1" ]; then say "[dry-run] $*"; else "$@"; fi
}

# ---------------------------------------------------------------- preflight
command -v hermes >/dev/null 2>&1 || {
  say "ERROR: 'hermes' CLI not found. Install Hermes first — this suite is an add-on, not a bundle."
  exit 1
}
command -v python3 >/dev/null 2>&1 || { say "ERROR: python3 not found."; exit 1; }
[ -d "$HERMES_HOME" ] || {
  say "ERROR: HERMES_HOME ($HERMES_HOME) does not exist. Run Hermes once first."
  exit 1
}
[ -f "$CONFIG" ] || { say "ERROR: config not found: $CONFIG"; exit 1; }

say "== validating config: $CONFIG"
python3 "$SCRIPT_DIR/scripts/validate_config.py" "$CONFIG"

# Resolve the profile names from the config (router + workers).
PROFILES="$(python3 - "$CONFIG" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
names = [(cfg.get("router") or {}).get("profile")]
names += [w.get("profile") for w in cfg.get("workers") or []]
print("\n".join(n for n in names if n))
PY
)"
ROUTER_PROFILE="$(printf '%s\n' "$PROFILES" | head -n 1)"

# ---------------------------------------------------------------- collisions
TARGETS="$HERMES_HOME/plugins/superagent
$HERMES_HOME/superagent"
for p in $PROFILES; do
  TARGETS="$TARGETS
$HERMES_HOME/profiles/$p"
done

COLLISIONS=0
printf '%s\n' "$TARGETS" | while IFS= read -r t; do
  [ -e "$t" ] && say "already exists: $t" || true
done
while IFS= read -r t; do
  if [ -e "$t" ]; then COLLISIONS=1; fi
done <<EOF
$TARGETS
EOF
if [ "$COLLISIONS" = "1" ] && [ "$FORCE" != "1" ]; then
  say "ERROR: target paths already exist (see above). Re-run with --force to replace the suite-owned copies, or run uninstall.sh first."
  exit 1
fi

TS="$(date +%Y%m%d%H%M%S)"
if [ "$COLLISIONS" = "1" ]; then
  BACKUP_DIR="$HERMES_HOME/superagent/backups/$TS"
  say "== backing up previous suite files to $BACKUP_DIR"
  run mkdir -p "$BACKUP_DIR"
  while IFS= read -r t; do
    if [ -e "$t" ]; then run cp -R "$t" "$BACKUP_DIR/"; fi
  done <<EOF
$TARGETS
EOF
fi

# ------------------------------------------------------------------- install
say "== installing plugin -> $HERMES_HOME/plugins/superagent"
run mkdir -p "$HERMES_HOME/plugins"
run rm -rf "$HERMES_HOME/plugins/superagent"
run cp -R "$SCRIPT_DIR/plugin/superagent" "$HERMES_HOME/plugins/superagent"
run rm -rf "$HERMES_HOME/plugins/superagent/__pycache__"

say "== rendering profiles -> $HERMES_HOME/profiles"
if [ "$DRY_RUN" = "1" ]; then
  say "[dry-run] python3 render_profiles.py --config $CONFIG --templates $SCRIPT_DIR/profiles --out $HERMES_HOME/profiles"
else
  python3 "$SCRIPT_DIR/scripts/render_profiles.py" \
    --config "$CONFIG" --templates "$SCRIPT_DIR/profiles" --out "$HERMES_HOME/profiles"
fi

say "== installing suite config -> $HERMES_HOME/superagent/superagent.yaml"
run mkdir -p "$HERMES_HOME/superagent"
run cp "$CONFIG" "$HERMES_HOME/superagent/superagent.yaml"

say "== installing router skill -> profile $ROUTER_PROFILE"
run mkdir -p "$HERMES_HOME/profiles/$ROUTER_PROFILE/skills/router-superagent"
run cp "$SCRIPT_DIR/plugin/superagent/skills/router/SKILL.md" \
  "$HERMES_HOME/profiles/$ROUTER_PROFILE/skills/router-superagent/SKILL.md"

# ------------------------------------------------------------------ manifest
say "== writing manifest"
if [ "$DRY_RUN" != "1" ]; then
  SUITE_VERSION="$(cat "$SCRIPT_DIR/VERSION" 2>/dev/null || echo 0.1.0)"
  TARGETS="$TARGETS" HERMES_HOME="$HERMES_HOME" SUITE_VERSION="$SUITE_VERSION" python3 - <<'PY'
import json, os, time
targets = [t for t in os.environ["TARGETS"].splitlines() if t.strip()]
manifest = {
    "suite": "hermes-superagent",
    "version": os.environ.get("SUITE_VERSION", "0.1.0"),
    "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "hermes_home": os.environ["HERMES_HOME"],
    "created_paths": targets,
    "cron": "manual — see docs/CONFIG.md (watchdog)",
}
path = os.path.join(os.environ["HERMES_HOME"], "superagent", "manifest.json")
with open(path, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2, ensure_ascii=False)
print(f"manifest: {path}")
PY
fi

# -------------------------------------------------------------------- smoke
say "== smoke check"
run python3 "$SCRIPT_DIR/scripts/validate_config.py" "$HERMES_HOME/superagent/superagent.yaml"

cat <<EOF

Done. Next steps:
  1. Put your API key(s) in the environment of each profile gateway, e.g.
     export the variable named by api_key_env in your config
     (DeepSeek example: SUPERAGENT_MAIN_API_KEY).
  2. Start the gateways for the router and worker profiles and send the
     router a task from the Hermes CLI.
  3. Optional: schedule the watchdog — see docs/CONFIG.md.
Uninstall at any time with ./uninstall.sh (removes only what the
manifest lists).
EOF
