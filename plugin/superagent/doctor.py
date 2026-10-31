"""Install doctor: whole-suite health check, in human sentences.

Every check below corresponds to a failure actually observed during
the first live install (2026-10-31 → 11-01). The design rule (see
docs/PRINCIPLES.md #5): an error must arrive as a sentence with the
fix attached — never as a log tail the user has to decode. So each
check returns {level, text, fix?} with level in ok|warn|error, and
the CLI prints them as prose.

Field failures encoded here:
  1. The API-key env var was set nowhere the gateway could see, so
     every model call went out with a placeholder key.
  2. Toolsets written under `agent.toolsets`, a key Hermes ignores —
     the Router silently got the full default toolset and no kanban.
  3. Clash/mihomo fake-IP DNS: public names resolve into
     198.18.0.0/15, Hermes' SSRF guard calls that "internal", and
     every web fetch is blocked unless the profile allows private
     URLs. Compounded by: profiles do not inherit the default
     profile's security setting.
  4. Rendered configs hand-edited in a rich-text editor arrived with
     curly quotes, and every quoted value was silently wrong.

Pure functions over plain data; the plugin gathers the data.
"""
import ipaddress

EXECUTION_TOOLSETS = {"terminal", "file", "web", "browser", "code_execution"}


def _finding(level, text, fix=None):
    f = {"level": level, "text": text}
    if fix:
        f["fix"] = fix
    return f


def check_config_loaded(cfg, router_profile=None, worker_count=0):
    if not cfg:
        return [_finding(
            "error",
            "套件配置没有加载（~/.hermes/superagent/superagent.yaml 不存在或读不出来）。",
            "在仓库目录运行 ./install.sh 完成安装；配置只改 superagent.yaml，不要改渲染出的 profile 文件。",
        )]
    return [_finding(
        "ok",
        f"配置已加载：Router 是 {router_profile or '?'},共 {worker_count} 个 worker。",
    )]


def check_key_env(providers, env_present):
    """env_present: {env var name: bool} — presence only, never values."""
    out = []
    for name, p in (providers or {}).items():
        var = (p or {}).get("api_key_env")
        if not var:
            out.append(_finding(
                "error", f"provider {name} 没有填 api_key_env（应填环境变量名，不是 key 本身）。"))
        elif not env_present.get(var):
            out.append(_finding(
                "error",
                f"环境变量 {var} 在全局和各 profile 的 .env 里都没找到——gateway 会带着占位 key 发请求，必然被拒。",
                f"把 key 写进 ~/.hermes/.env（一行 {var}=<你的key>），然后 hermes gateway restart。",
            ))
        else:
            out.append(_finding("ok", f"provider {name} 的 key 变量 {var} 已就位。"))
    return out


def check_router_toolsets(profile_name, profile_cfg):
    cfg = profile_cfg or {}
    agent = cfg.get("agent") or {}
    if "toolsets" in agent:
        return [_finding(
            "error",
            f"{profile_name} 的配置里还有 agent.toolsets——Hermes 不读这个键，工具集限制等于没写。",
            "升级到 v0.2.1+ 并重新 ./install.sh --force（新模板写 platform_toolsets）。",
        )]
    cli = ((cfg.get("platform_toolsets") or {}).get("cli")) or []
    if "kanban" not in cli:
        return [_finding(
            "error",
            f"{profile_name} 的 cli 工具集里没有 kanban——它建不了卡。",
            f"hermes -p {profile_name} tools enable kanban，然后开一个新会话。",
        )]
    extra = [t for t in cli if t in EXECUTION_TOOLSETS]
    if extra:
        return [_finding(
            "warn",
            f"{profile_name} 还带着执行工具（{', '.join(extra)}）——它可能绕过看板自己干活。",
            "用最新版重新安装，渲染出的 Router 只有 kanban + memory + skills。",
        )]
    return [_finding("ok", f"{profile_name} 工具集正确：只有 kanban + memory/skills，没有执行工具。")]


def check_worker_profile(profile_name, profile_cfg):
    cfg = profile_cfg or {}
    cli = ((cfg.get("platform_toolsets") or {}).get("cli")) or []
    if not cli:
        return [_finding(
            "warn",
            f"{profile_name} 没有 platform_toolsets.cli——被分发器拉起时 kanban 工具会自动补上，但直接开会话时它没有工作工具。",
            "重新运行 ./install.sh --force 重新渲染。",
        )]
    return [_finding("ok", f"{profile_name} 工具集已渲染（{', '.join(cli)}）。")]


def is_fake_ip(ip):
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network("198.18.0.0/15")
    except ValueError:
        return False


def check_fake_ip(resolved_ips, profiles_allow_private):
    """profiles_allow_private: {profile name: bool}."""
    fake = [ip for ip in (resolved_ips or []) if is_fake_ip(ip)]
    if not fake:
        return []
    lacking = [p for p, ok in (profiles_allow_private or {}).items() if not ok]
    if lacking:
        return [_finding(
            "error",
            f"这台机器的 DNS 是 fake-IP 模式（公网域名解析到 {fake[0]} 这类 198.18 段地址），"
            f"Hermes 的 SSRF 守卫会把所有网页抓取当成内网访问拦掉。以下 profile 还没放行：{', '.join(lacking)}。",
            "在 superagent.yaml 里设 security.allow_private_urls: true 后重新安装（会写进每个 profile；只在默认 profile 上设不算数，profile 之间不继承）。",
        )]
    return [_finding(
        "ok", "检测到 fake-IP DNS，各 profile 均已放行私网 URL，网页抓取不会被 SSRF 守卫误拦。")]


def check_private_base_url(providers):
    out = []
    for name, p in (providers or {}).items():
        url = (p or {}).get("base_url") or ""
        host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            continue
        if not ip.is_global:
            out.append(_finding(
                "warn",
                f"provider {name} 的端点在非公网地址（{host}）——模型调用不走 SSRF 守卫，这是允许的；只需确保这台机器能直连它（比如在同一个 tailnet 里）。",
            ))
    return out


def check_smart_quotes(profile_texts):
    out = []
    for profile, text in (profile_texts or {}).items():
        if text and ("“" in text or "”" in text):
            out.append(_finding(
                "error",
                f"{profile} 的 config.yaml 里有中文引号——多半是被富文本编辑器改过，所有带引号的值都会读错。",
                "不要手改渲染文件；改 superagent.yaml（用 nano/VS Code）后重新 ./install.sh --force。",
            ))
    return out


def check_board(counts):
    if counts is None:
        return [_finding(
            "warn",
            "看板还没初始化（没有 kanban.db）——第一张卡建出来时会自动生成，也可以先跑 hermes kanban init。",
        )]
    total = sum(counts.values())
    return [_finding("ok", f"看板存在，共 {total} 张卡：" +
                     "，".join(f"{k} {v}" for k, v in sorted(counts.items())))]


def summarize(findings):
    errors = sum(1 for f in findings if f["level"] == "error")
    warns = sum(1 for f in findings if f["level"] == "warn")
    if errors:
        return f"结论：{errors} 个问题需要处理（另有 {warns} 个提醒）。"
    if warns:
        return f"结论：没有硬伤，{warns} 个提醒值得看一眼。"
    return "结论：全部正常。"
