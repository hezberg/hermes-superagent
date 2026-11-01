#!/bin/sh
# Release helper: bump the version everywhere it is recorded, from
# the single source (the argument), then run the full test suite.
# VERSION is the only file a human edits by hand for a release;
# plugin.yaml and the plugin's PLUGIN_VERSION are kept in sync here,
# and the installer stamps the same value into installed copies.
#
# Usage: scripts/release.sh 0.5.0
set -eu
cd "$(dirname "$0")/.."
V="${1:?usage: scripts/release.sh X.Y.Z}"
printf '%s\n' "$V" > VERSION
sed -i.bak "s/^version: .*/version: $V/" plugin/superagent/plugin.yaml && rm -f plugin/superagent/plugin.yaml.bak
sed -i.bak "s/^PLUGIN_VERSION = \".*\"/PLUGIN_VERSION = \"$V\"/" plugin/superagent/__init__.py && rm -f plugin/superagent/__init__.py.bak
sed -i.bak "s/\"0\.[0-9]*\.[0-9]*\")/\"$V\")/" tests/test_plugin_register.py && rm -f tests/test_plugin_register.py.bak
python3 -m unittest discover -s tests
echo "Version $V set and tests green. Update CHANGELOG.md + README status line, then commit & push."
