"""工具系统

提供统一工具抽象 `Tool`、执行结果 `Result`、注册中心 `Registry`、
默认工具集构造与公共辅助函数。
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from micodeagent.llm import ToolDefinition

# 单个工具执行的默认超时秒数（不可配）
DEFAULT_TIMEOUT: float = 30.0


@dataclass
class Result:
    """工具执行结果——永远以值类型返回，从不抛 Python 异常给上层。"""

    content: str  # 回灌给模型的文本（已截断/带行号等）
    is_error: bool = False  # True 表示结构化错误，content 即错误描述


@runtime_checkable
class Tool(Protocol):
    """统一工具抽象

    每个工具暴露名称、描述、参数 Schema 和异步执行入口。
    execute 接受 raw JSON 字符串参数，超时由 Registry 层控制。
    read_only=True 表示只读工具（可并发执行 & Plan Mode 放行）。
    """

    read_only: bool

    def name(self) -> str:
        """模型看到的工具名，如 "read_file" """
        ...

    def description(self) -> str:
        """给模型的用途说明"""
        ...

    def parameters(self) -> dict[str, Any]:
        """手写 JSON Schema（type/properties/required/description）"""
        ...

    async def execute(self, args: str) -> Result:
        """执行工具，args 为 raw JSON 字符串"""
        ...


def _truncate(s: str, max_lines: int, max_chars: int) -> str:
    """按行数和字符数截断，超出尾部追加 [truncated] 标注。"""
    lines = s.split("\n")
    truncated = False

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars]
        truncated = True

    if truncated:
        result += "\n[truncated]"
    return result


class Registry:
    """集中登记工具、按名查找、导出定义、按名执行。"""

    def __init__(self) -> None:
        self._order: list[str] = []
        self._tools: dict[str, Tool] = {}

    def register(self, t: Tool) -> None:
        """注册工具，重名则抛 ValueError。"""
        name = t.name()
        if name in self._tools:
            raise ValueError(f"工具 '{name}' 已注册")
        self._order.append(name)
        self._tools[name] = t

    def get(self, name: str) -> Tool | None:
        """按名查找工具，未命中返回 None。"""
        return self._tools.get(name)

    def definitions(self) -> list[ToolDefinition]:
        """按注册顺序导出所有工具定义。"""
        return [
            ToolDefinition(
                name=t.name(),
                description=t.description(),
                input_schema=t.parameters(),
            )
            for t in (self._tools[n] for n in self._order)
        ]

    def read_only_definitions(self) -> list[ToolDefinition]:
        """Plan Mode：只导出 read_only==True 的工具定义，保留注册顺序。"""
        return [
            ToolDefinition(
                name=t.name(),
                description=t.description(),
                input_schema=t.parameters(),
            )
            for t in (self._tools[n] for n in self._order)
            if t.read_only
        ]

    def is_read_only(self, name: str) -> bool:
        """分批判定；未知工具返回 False（按串行处理）。"""
        t = self.get(name)
        return t is not None and t.read_only

    def count(self) -> int:
        """返回已注册工具数量。"""
        return len(self._tools)

    async def execute(self, name: str, args: str, timeout: float = DEFAULT_TIMEOUT) -> Result:
        """按名执行工具，带超时与异常兜底。

        未知工具 / 超时 / 异常均返回 Result(is_error=True)，
        不抛异常给上层。
        """
        tool = self.get(name)
        if tool is None:
            return Result(content=f"未知工具: {name}", is_error=True)

        try:
            return await asyncio.wait_for(tool.execute(args), timeout=timeout)
        except asyncio.TimeoutError:
            return Result(content=f"工具 {name} 执行超时（{timeout}s）", is_error=True)
        except Exception as e:
            return Result(content=f"工具 {name} 异常: {e}", is_error=True)


def new_default_registry() -> Registry:
    """构造并注册 6 个核心工具，返回 Registry。"""
    from micodeagent.tool.bash import BashTool
    from micodeagent.tool.edit_file import EditFileTool
    from micodeagent.tool.glob_tool import GlobTool
    from micodeagent.tool.grep_tool import GrepTool
    from micodeagent.tool.read_file import ReadFileTool
    from micodeagent.tool.write_file import WriteFileTool

    r = Registry()
    r.register(ReadFileTool())
    r.register(WriteFileTool())
    r.register(EditFileTool())
    r.register(BashTool())
    r.register(GlobTool())
    r.register(GrepTool())
    return r
