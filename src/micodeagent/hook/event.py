"""Hook 事件定义"""

from __future__ import annotations

from enum import Enum


class Event(str, Enum):
    """生命周期事件（11 个）。"""

    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    SESSION_RESUME = "SessionResume"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    PRE_USER_MESSAGE = "PreUserMessage"
    PRE_COMPACT = "PreCompact"
    POST_COMPACT = "PostCompact"
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    NOTIFICATION = "Notification"
    STOP = "Stop"


# 拦截类事件：工具执行前、用户提交时
BLOCKING_EVENTS: frozenset[Event] = frozenset({Event.PRE_TOOL_USE, Event.USER_PROMPT_SUBMIT})


def is_blocking(e: Event) -> bool:
    return e in BLOCKING_EVENTS


def parse_event(s: str) -> Event | None:
    try:
        return Event(s)
    except ValueError:
        return None
