#!/bin/sh
# hermes-superagent uninstaller — thin shim over scripts/uninstall.py.
# Removes exactly what the install state records; your config and
# history are kept unless you pass --purge.
exec python3 "$(dirname "$0")/scripts/uninstall.py" "$@"
