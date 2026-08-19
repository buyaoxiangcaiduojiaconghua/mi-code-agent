"""MCP 工具适配

把 SDK 返回的远端工具适配为 micodeagent Tool 协议。
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from typing import Any, Protocol

import mcp.types as mtypes

from micodeagent.tool import Result

# LLM 工具名合法字符
_VALID_NAME = re.compile(r"^[A-Za-z0-9_-]+$")

# 工具调用超时（模块级变量，便于单测临时改小）
call_timeout: float = 30.0

# 已告警过「非 text 内容块」的工具名（单 tool 限一次）
_non_text_warn_once: set[str] = set()


class CallerSession(Protocol):
    """远端会话的最小接口，便于单测注入 stub。"""

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None
    ) -> mtypes.CallToolResult: ...


@dataclass
class McpTool:
    """包装一个远端 MCP 工具，实现 micodeagent Tool 协议。"""

    full_name: str  # "mcp__<server>__<tool>"
    remote_name: str  # server 上的原始工具名
    desc: str
    schema: dict[str, Any]
    read_only: bool
    caller: CallerSession

    def name(self) -> str:
        return self.full_name

    def description(self) -> str:
        return self.desc

    def parameters(self) -> dict[str, Any]:
        return self.schema

    async def execute(self, args: str) -> Result:
        """调用远端工具，返回结构化结果。"""
        try:
            arg_map = json.loads(args) if args.strip() else None
        except json.JSONDecodeError:
            return Result(content="MCP 工具参数 JSON 解析失败", is_error=True)

        try:
            result = await asyncio.wait_for(
                self.caller.call_tool(self.remote_name, arg_map),
                timeout=call_timeout,
            )
        except asyncio.TimeoutError:
            return Result(content=f"MCP 工具调用超时 ({call_timeout}s)", is_error=True)
        except Exception as e:
            return Result(content=f"MCP 工具调用失败: {e}", is_error=True)

        texts: list[str] = []
        for block in result.content:
            if isinstance(block, mtypes.TextContent):
                texts.append(block.text)
            else:
                if self.full_name not in _non_text_warn_once:
                    _non_text_warn_once.add(self.full_name)
                    print(
                        f"[mcp] warn: tool {self.full_name} returned "
                        "non-text content blocks (dropped)",
                        file=sys.stderr,
                    )

        return Result(content="\n".join(texts), is_error=bool(result.is_error))


def adapt_tool(server_name: str, t: mtypes.Tool, session: CallerSession) -> McpTool | None:
    """把远端工具适配为 McpTool；非法名返回 None + 告警。"""
    full_name = f"mcp__{server_name}__{t.name}"

    if not _VALID_NAME.fullmatch(full_name):
        print(
            f"[mcp] warn: skip tool {full_name}: name contains illegal characters",
            file=sys.stderr,
        )
        return None

    description = t.description or f"来自 MCP server {server_name} 的工具 {t.name}"
    schema = dict(t.input_schema) if t.input_schema else {"type": "object"}
    read_only = bool(getattr(t, "annotations", None) and t.annotations.read_only_hint)

    return McpTool(
        full_name=full_name,
        remote_name=t.name,
        desc=description,
        schema=schema,
        read_only=read_only,
        caller=session,
    )
