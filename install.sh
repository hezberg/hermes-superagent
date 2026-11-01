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
CONFIG_EXPLICIT=0
DRY_RUN=0
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --config) CONFIG="$2"; CONFIG_EXPLICIT=1; shift 2 ;;
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

# Config source of truth: once the user has a filled-in copy installed
# under $HERMES_HOME/superagent/, that copy wins over any repo-side
# candidate — a git pull must never fight over the user's real config.
# First-install staging may live in config/superagent.local.yaml
# (gitignored); the tracked template is only the fallback.
if [ "$CONFIG_EXPLICIT" != "1" ] && [ -f "$SCRIPT_DIR/config/superagent.local.yaml" ]; then
  CONFIG="$SCRIPT_DIR/config/superagent.local.yaml"
fi
SUITE_CFG="$HERMES_HOME/superagent/superagent.yaml"
if [ "$CONFIG_EXPLICIT" != "1" ] && [ -f "$SUITE_CFG" ]; then
  CONFIG="$(python3 "$SCRIPT_DIR/scripts/pick_config.py" "$CONFIG" "$SUITE_CFG")"
fi
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

# Hermes plugins are opt-in: a plugin directory on disk is NOT loaded
# until its key is in plugins.enabled (the loader skips it silently).
# Enable it through Hermes' own tooling — without this step the whole
# command surface (status/doctor/digest/watchdog) silently does not
# exist, which is exactly what happened on the first live install.
say "== enabling plugin (hermes plugins enable superagent)"
if [ "$DRY_RUN" = "1" ]; then
  say "[dry-run] hermes plugins enable superagent"
elif ! hermes plugins enable superagent; then
  say "注意：'hermes plugins enable superagent' 没成功。Hermes 的插件是 opt-in 的，没启用就不会加载——看板分发主链路不受影响（靠 profile + 分发器），但 status/doctor/digest/watchdog 这些命令面不会出现。请手动跑一次：hermes plugins enable superagent，然后重启 gateway。"
fi

# Reminder tick: a no-agent cron script. Its stdout IS the delivery —
# Hermes' cron router sends printed lines to the user's platform, and
# a silent tick sends nothing. The ledger inside guarantees it only
# speaks when unclosed work genuinely needs the person.
say "== installing reminder tick script -> $HERMES_HOME/scripts/superagent-reminder-tick.py"
if [ "$DRY_RUN" = "1" ]; then
  say "[dry-run] install scripts/reminder_tick.py"
else
  mkdir -p "$HERMES_HOME/scripts"
  sed "s|__HERMES_HOME__|$HERMES_HOME|g" "$SCRIPT_DIR/scripts/reminder_tick.py" > "$HERMES_HOME/scripts/superagent-reminder-tick.py"
  chmod +x "$HERMES_HOME/scripts/superagent-reminder-tick.py"
fi
TARGETS="$TARGETS
$HERMES_HOME/scripts/superagent-reminder-tick.py"
say "== registering reminder cron (every 10m, no-agent)"
if [ "$DRY_RUN" = "1" ]; then
  say "[dry-run] hermes cron create \"every 10m\" --no-agent --script superagent-reminder-tick.py --deliver <platform>"
elif hermes cron list 2>/dev/null | grep -q "superagent-reminder-tick"; then
  say "reminder cron already registered; leaving it as-is"
elif hermes cron create "every 10m" --no-agent --script superagent-reminder-tick.py >/dev/null 2>&1; then
  say "reminder cron registered —— 但还没指定投递平台：跑 hermes cron list 找到它，用 hermes cron edit <id> --deliver <你的平台，如 feishu> 指过去，提醒才会真正发到你手上。"
else
  say "注意：提醒 cron 没注册成功（这个版本的 cron 命令面可能不同）。手动注册一条即可："
  say "  hermes cron create \"every 10m\" --no-agent --script superagent-reminder-tick.py --deliver <你的平台，如 feishu>"
  say "不注册也不影响其他功能，只是未闭环任务不会主动提醒。"
fi

say "== rendering profiles -> $HERMES_HOME/profiles"
if [ "$DRY_RUN" = "1" ]; then
  say "[dry-run] python3 render_profiles.py --config $CONFIG --templates $SCRIPT_DIR/profiles --out $HERMES_HOME/profiles"
else
  python3 "$SCRIPT_DIR/scripts/render_profiles.py" \
    --config "$CONFIG" --templates "$SCRIPT_DIR/profiles" --out "$HERMES_HOME/profiles"
fi

say "== installing suite config -> $HERMES_HOME/superagent/superagent.yaml"
run mkdir -p "$HERMES_HOME/superagent"
if [ "$CONFIG" = "$SUITE_CFG" ]; then
  say "(config already lives at the suite path; keeping it as-is)"
else
  run cp "$CONFIG" "$HERMES_HOME/superagent/superagent.yaml"
fi

say "== installing router skill -> profile $ROUTER_PROFILE"
run mkdir -p "$HERMES_HOME/profiles/$ROUTER_PROFILE/skills/router-superagent"
run cp "$SCRIPT_DIR/plugin/superagent/skills/router/SKILL.md" \
  "$HERMES_HOME/profiles/$ROUTER_PROFILE/skills/router-superagent/SKILL.md"

say "== installing worker skill -> worker profiles"
for p in $PROFILES; do
  [ "$p" = "$ROUTER_PROFILE" ] && continue
  run mkdir -p "$HERMES_HOME/profiles/$p/skills/worker-superagent"
  run cp "$SCRIPT_DIR/plugin/superagent/skills/worker/SKILL.md" \
    "$HERMES_HOME/profiles/$p/skills/worker-superagent/SKILL.md"
done

# Belt and braces: enable the kanban toolset on the router profile through
# Hermes' own tooling as well, so the Router can drive the board even if
# the platform_toolsets key in the rendered config is ever ignored.
say "== enabling kanban toolset on router profile via hermes tools"
if [ "$DRY_RUN" = "1" ]; then
  say "[dry-run] hermes -p $ROUTER_PROFILE tools enable kanban"
elif ! hermes -p "$ROUTER_PROFILE" tools enable kanban; then
  say "warning: 'hermes -p $ROUTER_PROFILE tools enable kanban' failed — enable the kanban toolset for that profile manually with: hermes -p $ROUTER_PROFILE tools"
fi
# Same, for the Feishu platform, so a chat entry is ready when the user
# wires one up (see SETUP.md §6). Soft failure: not every install wants
# a chat entry, and the platform name is version-dependent.
if [ "$DRY_RUN" = "1" ]; then
  say "[dry-run] hermes -p $ROUTER_PROFILE tools enable kanban --platform feishu"
elif ! hermes -p "$ROUTER_PROFILE" tools enable kanban --platform feishu 2>/dev/null; then
  say "note: 没能给 $ROUTER_PROFILE 预开飞书平台的 kanban 工具集（渲染配置里已经写了同一行，通常不影响）。若要用飞书入口，按 SETUP.md 第 6 节手动开一次即可。"
fi

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

say "== checking the plugin responds"
PLUGIN_OK=0
if [ "$DRY_RUN" = "1" ]; then
  say "[dry-run] hermes superagent status"
  PLUGIN_OK=1
elif hermes superagent status >/dev/null 2>&1; then
  PLUGIN_OK=1
  say "plugin OK: 'hermes superagent status' 可用（status / doctor / digest / watchdog 都走它）"
else
  say "注意：'hermes superagent status' 现在还不可用——这个 Hermes 版本可能还没加载插件。"
  say "看板分发主链路不依赖插件（靠 profile + gateway 分发器），可以先用；status/doctor/digest/watchdog 要等插件加载后才有。"
  say "排查时请保留这条命令的输出：grep -rin plugin ~/.hermes/logs/ | tail -20"
fi

cat <<EOF

Done. 这次生效的配置：$CONFIG
它已存到 $HERMES_HOME/superagent/superagent.yaml —— 以后以那份为准：
改配置就改它（或安装时 --config 指定），仓库模板被 git pull 覆盖也不会再冲掉你填好的值。

Next steps:
  1. API key：把每个 provider 的 key 写进 ~/.hermes/.env，一行一个：
       <api_key_env 里填的变量名>=<key 本身>
     然后运行：hermes gateway restart
  2. 体检：hermes superagent doctor —— 整套检查，人话结论 + 修法。
  3. 派活：hermes --profile $ROUTER_PROFILE，在对话里直接说任务即可。
     进度在 hermes dashboard 的 Kanban 页看；成果会记入
     $HERMES_HOME/superagent/journal.md。
Uninstall at any time with ./uninstall.sh (removes only what the
manifest lists).
EOF
