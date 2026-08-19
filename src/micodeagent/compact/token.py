"""Token 估算

锚定最近一次 provider usage + 之后新增消息的字符增量。
"""

from __future__ import annotations

import math

from micodeagent.compact.const import ESTIMATE_CHARS_PER_TOKEN
from micodeagent.llm import Message, Usage


def usage_anchor(u: Usage) -> int:
    """把 stream 尾事件中的 usage 合并成单一锚点值。"""
    return u.input_tokens + u.output_tokens + u.cache_read + u.cache_write


def message_chars(msgs: list[Message]) -> int:
    """计算消息列表的字符总量（UTF-8 字节）。"""
    total = 0
    for m in msgs:
        if m.content:
            total += len(m.content.encode("utf-8"))
        if m.tool_calls:
            for tc in m.tool_calls:
                total += len(tc.input.encode("utf-8"))
        if m.tool_results:
            for tr in m.tool_results:
                total += len(tr.content.encode("utf-8"))
    return total


def estimate_tokens(anchor: int, all_msgs: list[Message], anchor_msg_len: int) -> int:
    """锚定最近一次 provider usage + 之后新增消息的字符增量。

    anchor: 上一次主对话路径 stream 真实 usage 之和。
    all_msgs: 当前 conv.messages() 完整列表。
    anchor_msg_len: 当 anchor 被记录时 conv 的消息条数。
    """
    tail = all_msgs[max(0, anchor_msg_len) :]
    return anchor + math.ceil(message_chars(tail) / ESTIMATE_CHARS_PER_TOKEN)
