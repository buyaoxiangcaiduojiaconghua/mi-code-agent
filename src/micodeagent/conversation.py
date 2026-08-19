"""会话模块

在进程内维护单次会话的多轮对话历史（user/assistant/tool 交替）。
"""

import copy
from collections.abc import Callable

from micodeagent.llm import (
    ROLE_ASSISTANT,
    ROLE_TOOL,
    Message,
    ToolCall,
    ToolResult,
)


class Conversation:
    """单会话多轮历史"""

    def __init__(
        self,
        on_append: Callable[[Message], None] | None = None,
        on_replace: Callable[[list[Message]], None] | None = None,
    ) -> None:
        self._messages: list[Message] = []
        self._on_append = on_append
        self._on_replace = on_replace

    @classmethod
    def from_messages(
        cls,
        msgs: list[Message],
        on_append: Callable[[Message], None] | None = None,
        on_replace: Callable[[list[Message]], None] | None = None,
    ) -> "Conversation":
        """用已有消息列表构造会话。"""
        conv = cls(on_append=on_append, on_replace=on_replace)
        conv._messages = copy.deepcopy(list(msgs))
        return conv

    def add_user(self, text: str) -> None:
        """追加一条用户消息"""
        msg = Message(role="user", content=text)
        self._messages.append(msg)
        if self._on_append:
            self._on_append(msg)

    def add_assistant(self, text: str) -> None:
        """追加一条助手消息（纯文本）"""
        msg = Message(role="assistant", content=text)
        self._messages.append(msg)
        if self._on_append:
            self._on_append(msg)

    def add_assistant_with_tool_calls(self, text: str, calls: list[ToolCall]) -> None:
        """追加一条助手消息（含工具调用）"""
        msg = Message(role=ROLE_ASSISTANT, content=text, tool_calls=list(calls))
        self._messages.append(msg)
        if self._on_append:
            self._on_append(msg)

    def add_tool_results(self, results: list[ToolResult]) -> None:
        """追加一条工具结果消息"""
        msg = Message(role=ROLE_TOOL, tool_results=list(results))
        self._messages.append(msg)
        if self._on_append:
            self._on_append(msg)

    def messages(self) -> list[Message]:
        """返回完整历史的副本"""
        return list(self._messages)

    def last_role(self) -> str:
        """返回最后一条消息的 role；空历史返回 ""。"""
        return self._messages[-1].role if self._messages else ""

    def length(self) -> int:
        """返回消息条数"""
        return len(self._messages)

    def replace_history(self, msgs: list[Message]) -> None:
        """把内存列表整体替换为传入的 msgs（深拷贝）。"""
        new_list = copy.deepcopy(msgs)
        self._messages = new_list
        if self._on_replace:
            self._on_replace(list(self._messages))
