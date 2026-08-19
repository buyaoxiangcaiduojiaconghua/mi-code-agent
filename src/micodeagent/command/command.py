"""命令类型定义"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from micodeagent.command.ui import UI


class Kind(Enum):
    """命令执行模式"""

    LOCAL = "local"  # 纯本地操作
    UI = "ui"  # 影响界面状态
    PROMPT = "prompt"  # 把预设提示词送进对话交给 AI


Handler = Callable[["UI"], Awaitable[None]]


@dataclass(slots=True)
class Command:
    """单条 slash 命令。"""

    name: str
    description: str
    kind: Kind
    handler: Handler
    aliases: list[str] = field(default_factory=list)
    hidden: bool = False
