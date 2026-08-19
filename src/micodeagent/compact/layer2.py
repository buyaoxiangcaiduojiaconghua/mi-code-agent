"""第 2 层压缩：LLM 摘要 + PTL 重试 + 熔断"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from micodeagent.compact.recovery import build_recovery_attachment
from micodeagent.compact.summary_prompt import build_summary_prompt, extract_summary
from micodeagent.compact.token import estimate_tokens, message_chars
from micodeagent.llm import Message, PromptTooLongError, Request

if TYPE_CHECKING:
    from micodeagent.compact.compact import ManageInput

logger = logging.getLogger(__name__)


def pick_recent_tail(msgs: list[Message]) -> list[Message]:
    """从尾部取近期原文，满足 token 和条数两个下界。"""
    if not msgs:
        return []

    tokens = 0
    count = 0
    start_idx = len(msgs)
    for i in range(len(msgs) - 1, -1, -1):
        tokens += message_chars([msgs[i]]) / 3.5
        count += 1
        start_idx = i
        if tokens >= 10000 and count >= 5:
            break

    # 配对修正：如果截断点是 tool 消息，向前推到 assistant tool_use
    while start_idx > 0 and msgs[start_idx].role == "tool":
        start_idx -= 1

    return list(msgs[start_idx:])


def group_by_user_turn(msgs: list[Message]) -> list[list[Message]]:
    """按用户提交分组。"""
    groups = []
    current = []
    for m in msgs:
        if m.role == "user" and current:
            groups.append(current)
            current = []
        current.append(m)
    if current:
        groups.append(current)
    return groups


def _join_after_summary(summary_msg: Message, recent: list[Message]) -> list[Message]:
    """拼接摘要与近期原文，保证角色交替。"""
    result = [summary_msg]
    if not recent:
        return result
    if recent[0].role == "user":
        result.append(Message(role="assistant", content="（已加载上下文摘要与恢复信息。请继续。）"))
    result.extend(recent)
    return result


async def summarize_once(in_: "ManageInput", msgs: list[Message]) -> str:
    """发一次摘要请求。"""
    req = Request(messages=build_summary_prompt(msgs), tools=[])
    text_buf = []
    async for ev in in_.provider.stream(req):
        if ev.err is not None:
            raise ev.err
        if ev.text:
            text_buf.append(ev.text)
    return extract_summary("".join(text_buf))


async def ptl_retry(in_: "ManageInput", msgs: list[Message], first_err: Exception) -> str:
    """摘要请求自身 PTL 时按消息组丢弃重试。"""
    from micodeagent.compact.const import PTL_DROP_PERCENTAGE, PTL_RETRY_LIMIT

    groups = group_by_user_turn(msgs)
    attempts = 0

    while groups:
        if attempts < PTL_RETRY_LIMIT:
            if groups:
                groups = groups[1:]
        else:
            drop = max(1, math.ceil(len(groups) * PTL_DROP_PERCENTAGE))
            groups = groups[drop:]

        if not groups:
            break

        attempts += 1
        flat = [m for g in groups for m in g]
        try:
            return await summarize_once(in_, flat)
        except PromptTooLongError:
            continue
        except Exception:
            raise

    raise first_err


async def run_summary(in_: "ManageInput") -> list[Message]:
    """摘要 + 恢复 + 近期原文拼接。"""
    old_msgs = in_.conv.messages()
    recovery_snapshot = in_.recovery.snapshot()

    try:
        summary_text = await summarize_once(in_, old_msgs)
    except PromptTooLongError as e:
        summary_text = await ptl_retry(in_, old_msgs, e)

    recovery_text = build_recovery_attachment(recovery_snapshot, in_.tool_defs)

    combined = "## 历史会话摘要\n" + summary_text + "\n\n" + recovery_text
    summary_msg = Message(role="user", content=combined)

    recent = pick_recent_tail(old_msgs)
    return _join_after_summary(summary_msg, recent)


async def auto_compact(in_: "ManageInput") -> tuple[list[Message], int, int]:
    """自动摘要，失败计入熔断。"""
    before_tok = in_.estimated_token
    try:
        new_msgs = await run_summary(in_)
        in_.auto_tracking.record_success()
        after_tok = estimate_tokens(0, new_msgs, 0)
        return (new_msgs, before_tok, after_tok)
    except Exception:
        in_.auto_tracking.record_failure()
        raise


async def force_compact(in_: "ManageInput") -> tuple[list[Message], int, int]:
    """手动/紧急摘要，不计入熔断。"""
    before_tok = in_.estimated_token
    new_msgs = await run_summary(in_)
    after_tok = estimate_tokens(0, new_msgs, 0)
    return (new_msgs, before_tok, after_tok)
