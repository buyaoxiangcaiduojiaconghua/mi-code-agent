"""子 Agent 定义与来源类型"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Source(IntEnum):
    BUILTIN = 0
    USER = 1
    PROJECT = 2
    PLUGIN = 3

    def __str__(self) -> str:
        return {
            Source.BUILTIN: "builtin",
            Source.USER: "user",
            Source.PROJECT: "project",
            Source.PLUGIN: "plugin",
        }.get(self, "unknown")


@dataclass
class Definition:
    """子 Agent 角色定义。"""

    name: str
    description: str
    tools: list[str] = field(default_factory=list)  # 工具白名单
    disallowed_tools: list[str] = field(default_factory=list)  # 工具黑名单
    model: str = "inherit"  # inherit / haiku / sonnet / opus
    max_turns: int = 0  # 0 = 用全局默认
    permission_mode: str = "default"
    dont_ask: bool = False
    background: bool = False
    system_prompt: str = ""
    file_path: str = ""
    source: Source = Source.BUILTIN

    def is_fork(self) -> bool:
        return self.name == "__fork__"
