"""权限系统——公共类型与包门面

Mode 四档、Decision/Category/Outcome 枚举、ApprovalRequest 审批请求。
"""

import asyncio
from dataclasses import dataclass
from enum import IntEnum


class Mode(IntEnum):
    """权限模式四档"""

    DEFAULT = 0  # 只读 Allow / 文件写 Ask / 命令执行 Ask
    ACCEPT_EDITS = 1  # 文件写 Allow / 命令执行 Ask
    PLAN = 2  # 仅只读工具可见；矩阵同 default 作防御兜底
    BYPASS = 3  # 全 Allow（黑名单/沙箱仍拦）

    def __str__(self) -> str:
        return {
            Mode.DEFAULT: "default",
            Mode.ACCEPT_EDITS: "acceptEdits",
            Mode.PLAN: "plan",
            Mode.BYPASS: "bypassPermissions",
        }[self]


def parse_mode(s: str) -> tuple[Mode, bool]:
    """大小写不敏感识别四档名；未知返回 (Mode.DEFAULT, False)。"""
    lower = s.lower().strip()
    for m in Mode:
        if str(m).lower() == lower:
            return (m, True)
    return (Mode.DEFAULT, False)


def next_mode(m: Mode) -> Mode:
    """循环切换下一档：DEFAULT → ACCEPT_EDITS → PLAN → BYPASS → DEFAULT。"""
    return Mode((int(m) + 1) % 4)


class Decision(IntEnum):
    ALLOW = 0
    DENY = 1
    ASK = 2


class Category(IntEnum):
    READ = 0
    WRITE = 1
    EXEC = 2


class Outcome(IntEnum):
    """人在回路三选一"""

    DENY_ONCE = 0  # 拒绝本次
    ALLOW_ONCE = 1  # 允许本次（不留规则）
    ALLOW_FOREVER = 2  # 永久允许（写本地层文件）


class ApprovalError(Exception):
    """权限检查异常"""


@dataclass
class ApprovalRequest:
    """审批请求（agent 与 TUI 之间的通信载体）"""

    name: str  # 工具内部名
    args: str  # 参数预览
    reason: str  # 触发 Ask 的原因
    respond: asyncio.Future  # 单次未来量：TUI 回传用户选择


# Re-export Engine from engine module
from micodeagent.permission.engine import Engine as Engine  # noqa: E402, F401
from micodeagent.permission.engine import new_engine as new_engine  # noqa: E402, F401
