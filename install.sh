#!/bin/sh
# hermes-superagent installer — thin shim over scripts/install.py.
# One command for fresh install, upgrade, and repair: the Python
# installer converges the Hermes home to the desired state,
# verifies it, and reports what changed. See scripts/install.py.
exec python3 "$(dirname "$0")/scripts/install.py" "$@"
