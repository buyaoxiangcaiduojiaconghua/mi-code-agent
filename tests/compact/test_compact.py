"""compact 包核心单测——token/state/layer1/summary/recovery/layer2"""

import math

from micodeagent.compact.const import ESTIMATE_CHARS_PER_TOKEN
from micodeagent.compact.layer1 import build_preview, offload_and_snip, spill_single
from micodeagent.compact.layer2 import group_by_user_turn, pick_recent_tail
from micodeagent.compact.recovery import build_recovery_attachment
from micodeagent.compact.state import (
    CompactCircuitBreaker,
    ContentReplacementState,
    FileReadRecord,
    new_session_context,
)
from micodeagent.compact.summary_prompt import (
    build_summary_prompt,
    extract_summary,
    serialize_conversation,
)
from micodeagent.compact.token import estimate_tokens, usage_anchor
from micodeagent.llm import Message, ToolDefinition, ToolResult, Usage


class TestToken:
    def test_estimate_anchor(self):
        m = Message(role="user", content="x" * 35)
        result = estimate_tokens(1000, [m], 0)
        assert result == 1000 + math.ceil(35 / ESTIMATE_CHARS_PER_TOKEN)

    def test_estimate_empty(self):
        assert estimate_tokens(0, [], 0) == 0

    def test_usage_anchor_sum(self):
        u = Usage(input_tokens=100, output_tokens=50, cache_read=30, cache_write=20)
        assert usage_anchor(u) == 200


class TestState:
    def test_new_session_context(self, tmp_path):
        ctx = new_session_context(str(tmp_path))
        assert "-" in ctx.session_id
        import os

        assert os.path.isdir(ctx.spill_dir)

    def test_decide_once_kept_freeze(self):
        s = ContentReplacementState()
        calls = []
        assert s.decide_once("a", "orig", lambda: (calls.append(1), ("kept", ""))[1]) == "orig"
        # 第二次：decide 回调不再被调用，返回当前 content
        assert s.decide_once("a", "orig", lambda: (calls.append(1), ("kept", ""))[1]) == "orig"
        assert calls == [1]

    def test_decide_once_replaced_freeze(self):
        s = ContentReplacementState()
        assert s.decide_once("a", "orig", lambda: ("replaced", "PREV")) == "PREV"
        # 第二次不再调 decide，直接返回账本里的 preview
        assert s.decide_once("a", "orig", lambda: ("replaced", "NEW")) == "PREV"

    def test_breaker(self):
        b = CompactCircuitBreaker()
        b.record_failure()
        b.record_failure()
        assert not b.tripped()
        b.record_failure()
        assert b.tripped()
        b.record_success()
        assert not b.tripped()


class TestLayer1:
    def test_spill_idempotent(self, tmp_path):
        ctx = new_session_context(str(tmp_path))
        spill_single(ctx, "id1", "hello")
        import os
        from pathlib import Path

        p = Path(ctx.spill_dir) / "id1"
        mtime1 = os.stat(p).st_mtime_ns
        spill_single(ctx, "id1", "hello")
        mtime2 = os.stat(p).st_mtime_ns
        assert mtime1 == mtime2

    def test_offload_single_result(self, tmp_path):
        ctx = new_session_context(str(tmp_path))
        state = ContentReplacementState()
        content = "x" * 60000
        msgs = [
            Message(role="tool", tool_results=[ToolResult(tool_call_id="id1", content=content)])
        ]
        out = offload_and_snip(msgs, state, ctx)
        assert "[content offloaded]" in out[0].tool_results[0].content
        assert "60000 bytes" in out[0].tool_results[0].content

    def test_build_preview_stable(self):
        a = build_preview(100, "head", "/path/to/file")
        b = build_preview(100, "head", "/path/to/file")
        assert a == b
        assert "original size" in a
        assert "head preview" in a
        assert "文件读取工具" in a


class TestSummaryPrompt:
    def test_build_summary_shape(self):
        msgs = [Message(role="user", content="hi")]
        out = build_summary_prompt(msgs)
        assert len(out) == 1
        assert out[0].role == "user"
        assert "<summary>" in out[0].content
        assert "不要调用任何工具" in out[0].content

    def test_extract_summary(self):
        assert extract_summary("abc<summary>xx</summary>yy") == "xx"
        assert extract_summary("no tags here") == "no tags here"

    def test_serialize_deterministic(self):
        msgs = [Message(role="user", content="hi")]
        assert serialize_conversation(msgs) == serialize_conversation(msgs)


class TestRecovery:
    def test_build_attachment(self):
        rec = FileReadRecord(path="/a", content="x" * 100, timestamp=None)
        from datetime import datetime

        rec.timestamp = datetime.now()
        out = build_recovery_attachment(
            [rec], [ToolDefinition(name="read_file", description="r", input_schema={})]
        )
        assert "最近读过的文件" in out
        assert "当前可用工具" in out
        assert "边界提示" in out


class TestLayer2:
    def test_pick_recent_tail(self):
        msgs = [
            Message(role="user", content="u1"),
            Message(role="assistant", content="a1"),
            Message(role="tool", tool_results=[ToolResult(tool_call_id="1", content="r1")]),
            Message(role="user", content="u2"),
            Message(role="assistant", content="a2"),
            Message(role="tool", tool_results=[ToolResult(tool_call_id="2", content="r2")]),
        ]
        # 短消息不会触发下界，返回全部
        out = pick_recent_tail(msgs)
        assert len(out) == len(msgs)

    def test_group_by_user_turn(self):
        msgs = [
            Message(role="user", content="u"),
            Message(role="assistant", content="a"),
            Message(role="tool", tool_results=[ToolResult(tool_call_id="1", content="r")]),
            Message(role="user", content="u2"),
            Message(role="assistant", content="a2"),
        ]
        groups = group_by_user_turn(msgs)
        assert len(groups) == 2
        assert len(groups[0]) == 3
        assert len(groups[1]) == 2
