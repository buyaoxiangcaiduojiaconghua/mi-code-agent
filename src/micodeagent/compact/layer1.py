"""第 1 层压缩：单条工具结果落盘与预览替换"""

from __future__ import annotations

import copy
import logging
from pathlib import Path

from micodeagent.compact.const import (
    MESSAGE_AGGREGATE_LIMIT,
    PREVIEW_HEAD_BYTES,
    PREVIEW_HEAD_LINES,
    SINGLE_RESULT_LIMIT,
)
from micodeagent.compact.state import ContentReplacementState, SessionContext
from micodeagent.llm import Message

logger = logging.getLogger(__name__)


def spill_single(session: SessionContext, tool_use_id: str, content: str) -> None:
    """把单条工具结果写入 spill_dir，幂等。"""
    path = Path(session.spill_dir) / tool_use_id
    if path.exists():
        return
    path.write_bytes(content.encode("utf-8"))


def _head_preview(content: str) -> str:
    """取内容的前 PREVIEW_HEAD_LINES 行，再按 PREVIEW_HEAD_BYTES 字节裁剪。"""
    lines = content.splitlines(keepends=True)
    if len(lines) > PREVIEW_HEAD_LINES:
        lines = lines[:PREVIEW_HEAD_LINES]
    head = "".join(lines)
    head_bytes = head.encode("utf-8")
    if len(head_bytes) > PREVIEW_HEAD_BYTES:
        # 裁剪到 PREVIEW_HEAD_BYTES 字节，注意 UTF-8 边界
        head = head_bytes[:PREVIEW_HEAD_BYTES].decode("utf-8", errors="replace")
    return head


def build_preview(original_bytes: int, head: str, spill_path: str) -> str:
    """构造替换体字符串。"""
    return (
        f"[content offloaded] original size: {original_bytes} bytes\n"
        f"[saved to] {spill_path}\n"
        f"[head preview]\n"
        f"{head}\n"
        "完整内容已保存到上述路径，如需查看请用文件读取工具读取该路径，不要凭头部预览猜测全文"
    )


def offload_and_snip(
    msgs: list[Message],
    state: ContentReplacementState,
    session: SessionContext,
) -> list[Message]:
    """遍历 msgs，对 tool 消息的 tool_results 做超阈值落盘 + 替换。"""
    out = copy.deepcopy(msgs)

    for msg in out:
        if msg.role != "tool" or not msg.tool_results:
            continue

        # 已决策项：复用账本结果（不重新决策）
        for tr in msg.tool_results:
            if tr.tool_call_id in state._seen_ids:
                tr.content = state.decide_once(
                    tr.tool_call_id,
                    tr.content,
                    lambda: ("kept", ""),
                )

        # 收集未决策的候选项
        candidates = [tr for tr in msg.tool_results if tr.tool_call_id not in state._seen_ids]

        if not candidates:
            continue

        # 按字节倒序处理
        candidates.sort(key=lambda tr: len(tr.content.encode("utf-8")), reverse=True)

        # 计算当前聚合字节
        remaining_bytes = sum(len(tr.content.encode("utf-8")) for tr in msg.tool_results)

        for tr in candidates:
            content_bytes = len(tr.content.encode("utf-8"))

            should_spill = content_bytes > SINGLE_RESULT_LIMIT
            if not should_spill:
                should_spill = remaining_bytes > MESSAGE_AGGREGATE_LIMIT

            if should_spill:

                def _decide():
                    try:
                        spill_single(session, tr.tool_call_id, tr.content)
                    except OSError:
                        return ("skip", "")
                    spill_path = str(Path(session.spill_dir) / tr.tool_call_id)
                    return (
                        "replaced",
                        build_preview(
                            content_bytes,
                            _head_preview(tr.content),
                            spill_path,
                        ),
                    )

                tr.content = state.decide_once(tr.tool_call_id, tr.content, _decide)
                remaining_bytes -= content_bytes
                if tr.content.startswith("[content offloaded]"):
                    # 替换后字节数大幅减少
                    remaining_bytes = sum(len(t.content.encode("utf-8")) for t in msg.tool_results)
            else:

                def _keep():
                    return ("kept", "")

                tr.content = state.decide_once(tr.tool_call_id, tr.content, _keep)

    return out
