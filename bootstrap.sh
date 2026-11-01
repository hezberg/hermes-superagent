#!/bin/sh
# hermes-superagent bootstrap.
#
# Fetches the suite into its managed source home INSIDE Hermes' own
# directory (~/.hermes/superagent/src) and runs the installer from
# there. No checkout is left in your home directory or anywhere else
# you have to remember; later upgrades are just:
#
#   hermes superagent upgrade
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/hezberg/hermes-superagent/main/bootstrap.sh | sh
#
# Environment overrides: HERMES_HOME, SUPERAGENT_REPO_URL.
set -eu

HERMES_DIR="${HERMES_HOME:-$HOME/.hermes}"
SRC="$HERMES_DIR/superagent/src"
URL="${SUPERAGENT_REPO_URL:-https://github.com/hezberg/hermes-superagent.git}"

if [ -f "$SRC/scripts/install.py" ]; then
  if ! git -C "$SRC" pull --ff-only >/dev/null 2>&1; then
    # The managed clone holds no user data (config and history live
    # in the parent directory), so a stuck clone heals by re-cloning.
    echo "managed source clone is stuck; re-cloning it (your config is untouched)"
    rm -rf "$SRC"
    git clone --depth 1 "$URL" "$SRC"
  fi
else
  mkdir -p "$HERMES_DIR/superagent"
  git clone --depth 1 "$URL" "$SRC"
fi

exec python3 "$SRC/scripts/install.py" --home "$HERMES_DIR" "$@"
