"""规则持久化——人在回路「永久」写入本地配置"""

import os
from pathlib import Path

import yaml

from micodeagent.llm import ToolCall
from micodeagent.permission.rule import Rule
from micodeagent.permission.settings import (
    PermissionsBlock,
    Settings,
    extract_target,
    friendly_name,
    load_settings,
)


def rule_for(call: ToolCall, root: str) -> tuple[Rule, str, bool]:
    """生成精确规则

    Returns: (Rule, yaml_str, ok)
    """
    friendly = friendly_name(call.name)
    target, is_file, ok = extract_target(call)
    if not ok or not friendly:
        return (Rule("", "", False), "", False)

    if not is_file:
        # Bash 命令：转义 glob 元字符
        pattern = _escape_glob(target)
    else:
        try:
            rel = os.path.relpath(target, root)
            pattern = rel
        except ValueError:
            pattern = target

    rule_str = f"{friendly}({pattern})"
    return (Rule(tool=friendly, pattern=pattern, allow=True), rule_str, True)


def _escape_glob(s: str) -> str:
    """转义 glob 元字符防止泛化"""
    for ch in ["*", "?", "[", "]"]:
        s = s.replace(ch, f"[{ch}]")
    return s


def persist_local_allow(engine, call: ToolCall) -> None:
    """把精确 allow 规则写入本地层配置文件"""
    rule, rule_str, ok = rule_for(call, engine.root)
    if not ok:
        return

    try:
        settings = load_settings(engine.local_path)
    except Exception:
        settings = Settings()

    if settings.permissions is None:
        settings.permissions = PermissionsBlock()

    if rule_str not in settings.permissions.allow:
        settings.permissions.allow.append(rule_str)

    Path(engine.local_path).parent.mkdir(parents=True, exist_ok=True)
    data = {
        "default_mode": str(engine.start_mode),
        "permissions": {
            "allow": settings.permissions.allow,
            "deny": settings.permissions.deny,
        },
    }
    with open(engine.local_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)

    # 同步内存
    engine.local.allow.append(rule)
