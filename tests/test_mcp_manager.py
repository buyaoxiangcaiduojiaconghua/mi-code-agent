"""MCP 连接管理器单测——连接成功/失败/超时/close"""

import asyncio

import pytest

import micodeagent.mcp.manager as manager_mod
from micodeagent.mcp import Config, ServerConfig, new_manager
from micodeagent.mcp.tool import McpTool


class StubSession:
    async def call_tool(self, name, arguments):
        raise RuntimeError("not used")


def _make_tool(full_name):
    return McpTool(
        full_name=full_name,
        remote_name="t",
        desc="",
        schema={},
        read_only=False,
        caller=StubSession(),
    )


class TestManager:
    @pytest.mark.asyncio
    async def test_empty_config(self):
        cfg = Config()
        mgr = await new_manager(cfg, "test")
        assert mgr.tools() == []
        await mgr.close()

    @pytest.mark.asyncio
    async def test_failure_isolation(self, monkeypatch):
        """一个 server 失败，另一个成功，成功工具被注册。"""

        async def fake_do_connect(mgr, name, srv, version):
            if name == "bad":
                raise RuntimeError("boom")
            async with mgr._lock:
                mgr._tools.append(_make_tool(f"mcp__{name}__t"))

        monkeypatch.setattr(manager_mod, "_do_connect", fake_do_connect)

        cfg = Config(
            servers={
                "bad": ServerConfig(type="stdio", command="nonexistent"),
                "good": ServerConfig(type="stdio", command="ls"),
            }
        )
        mgr = await new_manager(cfg, "test")
        names = [t.name() for t in mgr.tools()]
        assert names == ["mcp__good__t"]
        await mgr.close()

    @pytest.mark.asyncio
    async def test_connect_timeout(self, monkeypatch, capsys):
        """连接卡住时超时收尾。"""

        async def hanging_do_connect(mgr, name, srv, version):
            await asyncio.Event().wait()

        monkeypatch.setattr(manager_mod, "_do_connect", hanging_do_connect)
        monkeypatch.setattr(manager_mod, "connect_timeout", 0.2)

        cfg = Config(servers={"hang": ServerConfig(type="stdio", command="ls")})
        mgr = await new_manager(cfg, "test")
        assert mgr.tools() == []
        assert "timeout" in capsys.readouterr().err
        await mgr.close()

    @pytest.mark.asyncio
    async def test_close_returns(self):
        """空 stack close 立即返回。"""
        cfg = Config()
        mgr = await new_manager(cfg, "test")
        await mgr.close()
