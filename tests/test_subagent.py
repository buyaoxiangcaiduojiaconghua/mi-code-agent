"""ch13 子 Agent 单测"""

import pytest

from micodeagent.agent.fork import build_forked_messages, is_fork_context
from micodeagent.llm import Message, ToolCall, ToolResult
from micodeagent.subagent.catalog import load_catalog
from micodeagent.subagent.definition import Source
from micodeagent.subagent.parser import parse_definition
from micodeagent.tool.filter import FilterParams, apply_agent_tool_filter


class TestParser:
    def test_parse_valid(self):
        d = parse_definition(
            b"---\nname: Explore\ndescription: read only\nmaxTurns: 30\n---\nbody text",
            "test",
            Source.BUILTIN,
        )
        assert d.name == "Explore"
        assert d.description == "read only"
        assert d.max_turns == 30
        assert d.system_prompt == "body text"

    def test_invalid_name(self):
        with pytest.raises(ValueError, match="invalid name"):
            parse_definition(b"---\nname: bad name\ndescription: d\n---\nx", "t", Source.BUILTIN)

    def test_missing_description(self):
        with pytest.raises(ValueError, match="missing description"):
            parse_definition(b"---\nname: ok\n---\nx", "t", Source.BUILTIN)

    def test_dont_ask(self):
        d = parse_definition(
            b"---\nname: x\ndescription: d\npermissionMode: dontAsk\n---\nx", "t", Source.BUILTIN
        )
        assert d.dont_ask is True

    def test_invalid_model_fallback(self, capsys):
        d = parse_definition(
            b"---\nname: x\ndescription: d\nmodel: bad\n---\nx", "t", Source.BUILTIN
        )
        assert d.model == "inherit"
        assert "invalid model" in capsys.readouterr().err


class TestCatalog:
    def test_builtin(self):
        c = load_catalog(".")
        names = [d.name for d in c.list()]
        assert "Explore" in names
        assert "Plan" in names
        assert "general-purpose" in names

    def test_fork_definition(self):
        c = load_catalog(".")
        fork = c.fork_definition()
        assert fork.is_fork()


class TestFilter:
    ALL = ["read_file", "write_file", "bash", "glob", "Agent", "mcp__x"]

    def test_default_removes_agent(self):
        r = apply_agent_tool_filter(FilterParams(all=self.ALL, source=1, background=False))
        assert "Agent" not in r
        assert "read_file" in r

    def test_background_intersection(self):
        r = apply_agent_tool_filter(FilterParams(all=self.ALL, source=1, background=True))
        assert "Agent" not in r
        assert "mcp__x" in r  # MCP 工具保留

    def test_blacklist(self):
        r = apply_agent_tool_filter(
            FilterParams(all=self.ALL, source=1, background=False, disallowed=["bash"])
        )
        assert "bash" not in r

    def test_whitelist(self):
        r = apply_agent_tool_filter(
            FilterParams(all=self.ALL, source=1, background=False, allowed=["read_file", "grep"])
        )
        assert r == ["read_file"]


class TestFork:
    def test_build_empty(self):
        msgs = build_forked_messages([], "do task")
        assert len(msgs) == 1
        assert "fork_boilerplate" in msgs[0].content
        assert "do task" in msgs[0].content

    def test_build_complete_pair(self):
        parent = [
            Message(role="user", content="hi"),
            Message(
                role="assistant",
                content="ok",
                tool_calls=[ToolCall(id="1", name="read_file", input="{}")],
            ),
            Message(role="tool", tool_results=[ToolResult(tool_call_id="1", content="x")]),
        ]
        msgs = build_forked_messages(parent, "task")
        assert len(msgs) == 4  # 3 条 parent + 1 条 user
        assert msgs[-1].role == "user"

    def test_build_orphan_tool_use(self):
        parent = [
            Message(
                role="assistant",
                content="ok",
                tool_calls=[ToolCall(id="1", name="read_file", input="{}")],
            ),
        ]
        msgs = build_forked_messages(parent, "task")
        # 追加 1 条 tool placeholder + 1 条 user
        assert msgs[1].role == "tool"
        assert msgs[1].tool_results[0].tool_call_id == "1"
        assert msgs[-1].role == "user"

    def test_is_fork_context(self):
        msgs = build_forked_messages([], "task")
        assert is_fork_context(msgs)
        assert not is_fork_context([Message(role="user", content="normal")])
