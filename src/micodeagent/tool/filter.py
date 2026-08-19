"""工具过滤：多层防线"""

from __future__ import annotations

from dataclasses import dataclass, field

# 全局禁止（所有子 Agent 都不能用）
ALL_AGENT_DISALLOWED_TOOLS: list[str] = ["Agent"]

# 自定义 Agent 额外禁止（本期为空）
CUSTOM_AGENT_DISALLOWED_TOOLS: list[str] = []

# 后台子 Agent 允许的工具白名单
ASYNC_AGENT_ALLOWED_TOOLS: list[str] = [
    "read_file",
    "write_file",
    "edit_file",
    "glob",
    "grep",
    "bash",
    "load_skill",
]


@dataclass
class FilterParams:
    all: list[str]  # registry 全部工具名
    source: int  # 1=builtin, 2=user, 3=project, 4=plugin
    background: bool
    allowed: list[str] = field(default_factory=list)
    disallowed: list[str] = field(default_factory=list)


def is_mcp_or_skill(name: str) -> bool:
    return name.startswith("mcp__")


def apply_agent_tool_filter(p: FilterParams) -> list[str]:
    """按 spec F30 顺序过滤工具。"""
    result = list(p.all)

    # 过滤 1：去全局禁止
    result = [n for n in result if n not in ALL_AGENT_DISALLOWED_TOOLS]

    # 过滤 2：非 builtin 去自定义禁止
    if p.source >= 2:
        result = [n for n in result if n not in CUSTOM_AGENT_DISALLOWED_TOOLS]

    # 过滤 3：后台交集
    if p.background:
        allowed_bg = set(ASYNC_AGENT_ALLOWED_TOOLS)
        result = [n for n in result if n in allowed_bg or is_mcp_or_skill(n)]

    # 过滤 4：去黑名单
    result = [n for n in result if n not in p.disallowed]

    # 过滤 5：白名单交集
    if p.allowed:
        result = [n for n in result if n in p.allowed]

    return result
