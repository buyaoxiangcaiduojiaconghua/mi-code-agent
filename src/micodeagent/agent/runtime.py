"""Agent 会话运行时状态容器"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from micodeagent.compact import (
    CompactCircuitBreaker,
    ContentReplacementState,
    RecoveryState,
    SessionContext,
    new_session_context,
)


@dataclass
class SessionRuntime:
    """跨 run 持有的长生命周期状态。"""

    replacement: ContentReplacementState
    recovery: RecoveryState
    auto_tracking: CompactCircuitBreaker
    session: SessionContext
    context_window: int = 200000
    usage_anchor: int = 0  # 上一次主对话路径 stream 真实 usage 之和
    anchor_msg_len: int = 0  # anchor 当时 Conversation 消息条数
    turn_count: int = 0
    pending_reminders: list[str] = field(default_factory=list)
    hook_engine: object = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def reset_for_new_session(self, ses_ctx: SessionContext) -> None:
        """原子重置为初始状态，session 指向新会话。"""
        self.replacement = ContentReplacementState()
        self.recovery = RecoveryState()
        self.auto_tracking = CompactCircuitBreaker()
        self.session = ses_ctx
        self.usage_anchor = 0
        self.anchor_msg_len = 0
        self.turn_count = 0
        self.pending_reminders = []

    def append_reminders(self, prompts: list[str]) -> None:
        self.pending_reminders.extend(prompts)

    def take_reminders(self) -> list[str]:
        prompts = self.pending_reminders
        self.pending_reminders = []
        return prompts


def default_runtime(workspace: str = ".") -> SessionRuntime:
    """构造一个默认的 SessionRuntime。"""
    return SessionRuntime(
        replacement=ContentReplacementState(),
        recovery=RecoveryState(),
        auto_tracking=CompactCircuitBreaker(),
        session=new_session_context(workspace),
    )
