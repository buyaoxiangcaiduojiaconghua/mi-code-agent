"""上下文管理子包

两层压缩 + 恢复 + 手动/紧急入口。
"""

from micodeagent.compact.compact import ManageInput, ManageOutput, TriggerKind, manage_context
from micodeagent.compact.state import (
    CompactCircuitBreaker,
    ContentReplacementState,
    RecoveryState,
    SessionContext,
    new_session_context,
)

__all__ = [
    "manage_context",
    "ManageInput",
    "ManageOutput",
    "TriggerKind",
    "ContentReplacementState",
    "CompactCircuitBreaker",
    "RecoveryState",
    "SessionContext",
    "new_session_context",
]
