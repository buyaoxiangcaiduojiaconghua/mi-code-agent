"""会话加载恢复"""

from __future__ import annotations

import json
import os

from micodeagent.llm import Message, ToolCall, ToolResult


def load_session(session_dir: str) -> list[Message]:
    """逐行读取 JSONL，恢复消息列表（坏行跳过、孤立截断）。"""
    path = os.path.join(session_dir, "conversation.jsonl")
    if not os.path.exists(path):
        return []

    msgs: list[Message] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue  # 坏行跳过

            if data.get("type") == "compact":
                msgs = []  # 压缩标记：清空，从后重新构建
                continue

            role = data.get("role")
            if role == "user" or role == "assistant":
                msg = Message(role=role, content=data.get("content", ""))
                if data.get("tool_calls"):
                    msg.tool_calls = [
                        ToolCall(id=c["id"], name=c["name"], input=c["input"])
                        for c in data["tool_calls"]
                    ]
                msgs.append(msg)
            elif role == "tool":
                msg = Message(role="tool")
                if data.get("tool_results"):
                    msg.tool_results = [
                        ToolResult(
                            tool_call_id=r["tool_call_id"],
                            content=r.get("content", ""),
                            is_error=r.get("is_error", False),
                        )
                        for r in data["tool_results"]
                    ]
                msgs.append(msg)

    return _truncate_orphaned_tool_calls(msgs)


def _truncate_orphaned_tool_calls(msgs: list[Message]) -> list[Message]:
    """如果最后一条 assistant 带 tool_calls 但无对应 tool 消息，截断。"""
    if not msgs:
        return msgs
    last = msgs[-1]
    if last.role == "assistant" and last.tool_calls:
        return msgs[:-1]
    return msgs
