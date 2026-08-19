"""配置加载与映射

friendly_name、categorize、extract_target、Settings 加载。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from micodeagent.llm import ToolCall
from micodeagent.permission import Category
from micodeagent.permission.rule import RuleSet, parse_rule

# 友好名映射：内部名 → 友好名
_FRIENDLY_MAP = {
    "bash": "Bash",
    "read_file": "Read",
    "write_file": "Write",
    "edit_file": "Edit",
    "glob": "Glob",
    "grep": "Grep",
}


def friendly_name(internal: str) -> str:
    """内部名 → 友好名"""
    return _FRIENDLY_MAP.get(internal, internal)


def categorize(internal: str, read_only: bool) -> Category:
    """判定工具类别"""
    if read_only:
        return Category.READ
    if internal in ("write_file", "edit_file"):
        return Category.WRITE
    return Category.EXEC


def extract_target(call: ToolCall) -> tuple[str, bool, bool]:
    """提取工具的匹配目标和文件标志

    Returns: (target, is_file, ok)
    """
    try:
        if isinstance(call.input, str):
            params = json.loads(call.input)
        else:
            params = call.input if isinstance(call.input, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return ("", False, False)

    name = call.name

    if name in ("read_file", "write_file", "edit_file"):
        path = params.get("path", "")
        if not path:
            return ("", True, False)
        return (path, True, True)

    elif name in ("glob", "grep"):
        path = params.get("path", ".")
        return (path, True, True)

    elif name == "bash":
        command = params.get("command", "")
        return (command, False, bool(command))

    else:
        return ("", False, False)


class SettingsError(Exception):
    """配置加载错误"""


@dataclass
class PermissionsBlock:
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)


@dataclass
class Settings:
    default_mode: str = ""
    permissions: PermissionsBlock = field(default_factory=PermissionsBlock)


def load_settings(path: str) -> Settings:
    """加载 YAML 配置文件"""
    p = Path(path)
    if not p.exists():
        return Settings()

    try:
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise SettingsError(f"YAML 解析失败: {path}: {e}")

    if data is None:
        return Settings()

    perms_data = data.get("permissions", {})
    if not isinstance(perms_data, dict):
        perms_data = {}

    return Settings(
        default_mode=str(data.get("default_mode", "")),
        permissions=PermissionsBlock(
            allow=list(perms_data.get("allow", [])),
            deny=list(perms_data.get("deny", [])),
        ),
    )


def to_rule_set(s: Settings) -> RuleSet:
    """Settings → RuleSet"""
    rs = RuleSet()
    for item in s.permissions.allow:
        rule, ok = parse_rule(item)
        if ok and rule.tool:
            rs.allow.append(rule)
    for item in s.permissions.deny:
        rule, ok = parse_rule(item)
        if ok and rule.tool:
            rule.allow = False
            rs.deny.append(rule)
    return rs
