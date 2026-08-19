"""Fork 路径辅助函数"""

from __future__ import annotations

import copy

from micodeagent.llm import Message, ToolResult

FORK_BOILERPLATE_TAG = "<fork_boilerplate>"

FORK_BOILERPLATE = """<fork_boilerplate>
你是一个 Fork 出来的工作进程。你不是主 Agent。
规则（不可协商）：
1. 不能再 Fork（调用 Agent 工具会被拦截）。
2. 不要对话、不要提问、不要请求确认。
3. 直接使用工具：读文件、搜索代码、做修改。
4. 严格限制在你被分配的任务范围内。
5. 最终报告以 "Scope:" 开头，500 字以内。
</fork_boilerplate>

"""


def build_forked_messages(parent_msgs: list[Message], task: str) -> list[Message]:
    """构造 Fork 子对话消息：补全未配对 tool_use + 追加 task。"""
    cloned = copy.deepcopy(parent_msgs)

    # 找末尾未配对的 tool_use
    consumed_ids: set[str] = set()
    for m in cloned:
        if m.role == "tool" and m.tool_results:
            for r in m.tool_results:
                consumed_ids.add(r.tool_call_id)

    orphan_ids = []
    for m in reversed(cloned):
        if m.role == "assistant" and m.tool_calls:
            for c in m.tool_calls:
                if c.id not in consumed_ids:
                    orphan_ids.insert(0, c.id)

    if orphan_ids:
        placeholders = [
            ToolResult(tool_call_id=tid, content="[forked, skipped]", is_error=True)
            for tid in orphan_ids
        ]
        cloned.append(Message(role="tool", tool_results=placeholders))

    cloned.append(Message(role="user", content=FORK_BOILERPLATE + task))
    return cloned


def is_fork_context(msgs: list[Message]) -> bool:
    """判断消息是否来自 Fork 上下文。"""
    for m in msgs:
        if FORK_BOILERPLATE_TAG in (m.content or ""):
            return True
    return False
