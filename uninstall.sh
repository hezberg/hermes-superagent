#!/usr/bin/env bash
# hermes-superagent uninstaller.
#
# Removes exactly the paths recorded in the install manifest
# ($HERMES_HOME/superagent/manifest.json) and nothing else. Pre-existing
# Hermes files are never touched — the installer never modified any.
# The manifest lives inside $HERMES_HOME/superagent, which is itself one
# of the recorded paths, so it is read first and removed last.
#
# Usage: ./uninstall.sh [--dry-run]
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

say() { printf '%s\n' "$*"; }
MANIFEST="$HERMES_HOME/superagent/manifest.json"

[ -f "$MANIFEST" ] || {
  say "ERROR: no manifest at $MANIFEST — nothing recorded to uninstall."
  say "If a previous install was interrupted, remove these paths by hand after checking them:"
  say "  $HERMES_HOME/plugins/superagent"
  say "  $HERMES_HOME/superagent"
  say "  $HERMES_HOME/profiles/sa-router, sa-worker-* (only if this suite created them)"
  exit 1
}

PATHS="$(python3 - "$MANIFEST" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
for p in m.get("created_paths", []):
    print(p)
PY
)"

say "== removing paths recorded in the manifest"
printf '%s\n' "$PATHS" | while IFS= read -r p; do
  [ -n "$p" ] || continue
  case "$p" in
    "$HERMES_HOME"/*) : ;;
    *) say "REFUSING path outside HERMES_HOME: $p"; exit 1 ;;
  esac
done
while IFS= read -r p; do
  [ -n "$p" ] || continue
  if [ "$p" = "$HERMES_HOME/superagent" ]; then continue; fi # suite dir last
  if [ -e "$p" ]; then
    if [ "$DRY_RUN" = "1" ]; then say "[dry-run] rm -rf $p"; else rm -rf "$p"; say "removed: $p"; fi
  else
    say "already gone: $p"
  fi
done <<EOF
$PATHS
EOF
if [ -e "$HERMES_HOME/superagent" ]; then
  if [ "$DRY_RUN" = "1" ]; then
    say "[dry-run] rm -rf $HERMES_HOME/superagent"
  else
    rm -rf "$HERMES_HOME/superagent"
    say "removed: $HERMES_HOME/superagent"
  fi
fi

say "== verifying"
LEFT=0
while IFS= read -r p; do
  [ -n "$p" ] || continue
  if [ -e "$p" ]; then say "STILL PRESENT: $p"; LEFT=1; fi
done <<EOF
$PATHS
EOF
if [ "$LEFT" = "0" ]; then
  say "Clean: every recorded path is gone. Your Hermes installation is untouched."
else
  say "Some paths remain (see above)."
  exit 1
fi
say "Note: if a reminder cron job was registered (hermes cron list shows superagent-reminder-tick), remove that job too — uninstall deletes the script it runs, but the job entry is Hermes' own record."
