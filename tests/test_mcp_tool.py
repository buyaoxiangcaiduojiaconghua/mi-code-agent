"""MCP 工具适配单测——命名/字段/execute 各分支"""

import asyncio

import mcp.types as mtypes
import pytest

from micodeagent.mcp.tool import adapt_tool


def _make_tool(name="echo", description="echo tool", schema=None, read_only_hint=None):
    annotations = None
    if read_only_hint is not None:
        annotations = mtypes.ToolAnnotations(read_only_hint=read_only_hint)
    return mtypes.Tool(
        name=name,
        description=description,
        input_schema=schema or {"type": "object"},
        annotations=annotations,
    )


class StubSession:
    def __init__(self, result=None, error=None, delay=None):
        self.result = result
        self.error = error
        self.delay = delay

    async def call_tool(self, name, arguments):
        if self.delay is not None:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.result


class TestAdapt:
    def test_name_prefix(self):
        t = _make_tool()
        tool = adapt_tool("github", t, StubSession())
        assert tool is not None
        assert tool.name() == "mcp__github__echo"

    def test_illegal_chars_skipped(self, capsys):
        t = _make_tool(name="bad.name")
        tool = adapt_tool("github", t, StubSession())
        assert tool is None
        assert "warn" in capsys.readouterr().err

    def test_description_fallback(self):
        t = _make_tool(description="")
        tool = adapt_tool("github", t, StubSession())
        assert tool.description()

    def test_schema_passthrough(self):
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        t = _make_tool(schema=schema)
        tool = adapt_tool("github", t, StubSession())
        assert tool.parameters() == schema

    def test_read_only_hint_true(self):
        t = _make_tool(read_only_hint=True)
        tool = adapt_tool("github", t, StubSession())
        assert tool.read_only is True

    def test_read_only_hint_none(self):
        t = _make_tool(read_only_hint=None)
        tool = adapt_tool("github", t, StubSession())
        assert tool.read_only is False


class TestExecute:
    def _make_tool(self, session):
        return adapt_tool("srv", _make_tool(), session)

    @pytest.mark.asyncio
    async def test_success_multi_text(self):
        result = mtypes.CallToolResult(
            content=[
                mtypes.TextContent(type="text", text="hello"),
                mtypes.TextContent(type="text", text="world"),
            ],
            is_error=False,
        )
        tool = self._make_tool(StubSession(result=result))
        r = await tool.execute('{"a": 1}')
        assert not r.is_error
        assert r.content == "hello\nworld"

    @pytest.mark.asyncio
    async def test_remote_is_error(self):
        result = mtypes.CallToolResult(
            content=[mtypes.TextContent(type="text", text="boom")],
            is_error=True,
        )
        tool = self._make_tool(StubSession(result=result))
        r = await tool.execute("{}")
        assert r.is_error
        assert r.content == "boom"

    @pytest.mark.asyncio
    async def test_protocol_error(self):
        tool = self._make_tool(StubSession(error=RuntimeError("conn lost")))
        r = await tool.execute("{}")
        assert r.is_error
        assert "失败" in r.content

    @pytest.mark.asyncio
    async def test_timeout(self, monkeypatch):
        import micodeagent.mcp.tool as tool_mod

        monkeypatch.setattr(tool_mod, "call_timeout", 0.2)
        tool = self._make_tool(StubSession(delay=10, result=mtypes.CallToolResult(content=[])))
        r = await tool.execute("{}")
        assert r.is_error
        assert "超时" in r.content

    @pytest.mark.asyncio
    async def test_non_text_dropped(self, capsys):
        # 一个 text + 一个 image 块
        result = mtypes.CallToolResult(
            content=[
                mtypes.TextContent(type="text", text="keep"),
                mtypes.ImageContent(type="image", data="x", mimeType="image/png"),
            ],
            is_error=False,
        )
        tool = self._make_tool(StubSession(result=result))
        r = await tool.execute("{}")
        assert r.content == "keep"
        assert "non-text" in capsys.readouterr().err
