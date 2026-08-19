"""MCP 连接管理器

并发连接所有 server，缓存会话，统一关闭。
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

import mcp.types as mtypes
from mcp import ClientSession

from micodeagent.mcp.config import Config, ServerConfig
from micodeagent.mcp.tool import McpTool, adapt_tool

# 模块级变量（非常量，便于单测临时改小）
connect_timeout: float = 30.0
close_timeout: float = 5.0


@dataclass
class _Session:
    name: str
    session: ClientSession


@dataclass
class Manager:
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _sessions: list[_Session] = field(default_factory=list)
    _tools: list[McpTool] = field(default_factory=list)
    _stack: AsyncExitStack = field(default_factory=AsyncExitStack)

    def tools(self) -> list[McpTool]:
        """返回适配好的工具列表副本。"""
        return list(self._tools)

    async def close(self) -> None:
        """关闭所有会话，5s 兜底。"""
        try:
            await asyncio.wait_for(self._stack.aclose(), timeout=close_timeout)
        except asyncio.TimeoutError:
            print(
                f"[mcp] warn: close timeout ({close_timeout}s), some sessions may leak",
                file=sys.stderr,
            )


async def new_manager(cfg: Config, version: str) -> Manager:
    """并发连接所有 server，每个 30s 超时，失败仅跳过。"""
    mgr = Manager()
    await mgr._stack.__aenter__()

    tasks = [
        asyncio.create_task(_connect_one(mgr, name, srv, version))
        for name, srv in cfg.servers.items()
    ]
    await asyncio.gather(*tasks, return_exceptions=True)

    mgr._tools.sort(key=lambda t: t.full_name)
    return mgr


async def _connect_one(mgr: Manager, name: str, srv: ServerConfig, version: str) -> None:
    """连接单个 server，超时/失败仅告警不抛出。"""
    try:
        await asyncio.wait_for(
            _do_connect(mgr, name, srv, version),
            timeout=connect_timeout,
        )
    except asyncio.TimeoutError:
        print(
            f"[mcp] warn: connect server {name} timeout after {connect_timeout}s",
            file=sys.stderr,
        )
    except Exception as e:
        print(f"[mcp] warn: connect server {name} failed: {e}", file=sys.stderr)


async def _do_connect(mgr: Manager, name: str, srv: ServerConfig, version: str) -> None:
    """建立连接、握手、列工具、适配。"""
    if srv.type == "stdio":
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=srv.command,
            args=srv.args,
            env={**os.environ, **srv.env},
        )
        ctx = stdio_client(params)
    else:  # http
        from mcp.client.streamable_http import streamable_http_client

        if srv.headers:
            import httpx2

            http_client = httpx2.AsyncClient(headers=srv.headers)
            await mgr._stack.enter_async_context(http_client)
            ctx = streamable_http_client(srv.url, http_client=http_client)
        else:
            ctx = streamable_http_client(srv.url)

    transport = await mgr._stack.enter_async_context(ctx)
    read, write = transport[0], transport[1]

    session = await mgr._stack.enter_async_context(
        ClientSession(
            read,
            write,
            client_info=mtypes.Implementation(name="micodeagent", version=version),
        )
    )

    await session.initialize()
    listed = await session.list_tools()

    tools: list[McpTool] = []
    for t in listed.tools:
        adapted = adapt_tool(name, t, session)
        if adapted is not None:
            tools.append(adapted)

    async with mgr._lock:
        mgr._sessions.append(_Session(name=name, session=session))
        mgr._tools.extend(tools)
