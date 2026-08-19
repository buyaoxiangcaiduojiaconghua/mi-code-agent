"""上下文管理编排入口"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from micodeagent.compact.const import AUTO_SAFETY_MARGIN, SUMMARY_RESERVE
from micodeagent.compact.layer1 import offload_and_snip
from micodeagent.compact.layer2 import auto_compact, force_compact
from micodeagent.compact.state import (
    CompactCircuitBreaker,
    ContentReplacementState,
    RecoveryState,
    SessionContext,
)
from micodeagent.compact.token import estimate_tokens
from micodeagent.llm import ToolDefinition

if TYPE_CHECKING:
    from micodeagent.conversation import Conversation
    from micodeagent.llm import Provider

logger = logging.getLogger(__name__)


class TriggerKind(Enum):
    AUTO = "auto"
    MANUAL = "manual"
    EMERGENCY = "emergency"


@dataclass
class ManageInput:
    conv: "Conversation"
    provider: "Provider"
    context_window: int
    tool_defs: list[ToolDefinition]
    replacement: ContentReplacementState
    recovery: RecoveryState
    auto_tracking: CompactCircuitBreaker
    session: SessionContext
    usage_anchor: int
    anchor_msg_len: int
    estimated_token: int
    trigger: TriggerKind


@dataclass
class ManageOutput:
    before_tokens: int
    after_tokens: int


async def manage_context(in_: ManageInput) -> ManageOutput:
    """Agent 每轮请求前必调的唯一入口。"""
    if in_.trigger == TriggerKind.MANUAL:
        # 跳过 layer1、阈值、熔断，直接 force_compact
        new_msgs, before, after = await force_compact(in_)
        in_.conv.replace_history(new_msgs)
        return ManageOutput(before_tokens=before, after_tokens=after)

    if in_.trigger == TriggerKind.EMERGENCY:
        # 先强制跑一次 layer1 把大工具结果挪走
        layer1_out = offload_and_snip(in_.conv.messages(), in_.replacement, in_.session)
        in_.conv.replace_history(layer1_out)
        new_msgs, before, after = await force_compact(in_)
        in_.conv.replace_history(new_msgs)
        return ManageOutput(before_tokens=before, after_tokens=after)

    # AUTO 路径
    # a. layer1
    layer1_out = offload_and_snip(in_.conv.messages(), in_.replacement, in_.session)
    in_.conv.replace_history(layer1_out)

    # b. 重估 token
    est = estimate_tokens(in_.usage_anchor, layer1_out, in_.anchor_msg_len)

    # c. sanity check
    if in_.context_window <= SUMMARY_RESERVE + AUTO_SAFETY_MARGIN:
        logger.warning("context_window too small, skipping auto layer2")
        return ManageOutput(before_tokens=in_.estimated_token, after_tokens=est)

    threshold = in_.context_window - SUMMARY_RESERVE - AUTO_SAFETY_MARGIN
    if est < threshold or in_.auto_tracking.tripped():
        return ManageOutput(before_tokens=in_.estimated_token, after_tokens=est)

    # d. auto_compact
    try:
        new_msgs, before, after = await auto_compact(in_)
        in_.conv.replace_history(new_msgs)
        return ManageOutput(before_tokens=before, after_tokens=after)
    except Exception:
        return ManageOutput(before_tokens=in_.estimated_token, after_tokens=est)
