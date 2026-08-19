"""LLM 协议层

定义协议无关的 `Provider` Protocol、统一的消息与流式事件类型、
工具调用相关类型、token 用量类型与请求结构，以及按配置构造适配器的工厂函数。
上层无需感知具体协议。
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from micodeagent.config import ProviderConfig

# ═══════════════════════════════════════════════════════════════════
# 哨兵异常
# ═══════════════════════════════════════════════════════════════════


class PromptTooLongError(Exception):
    """Provider 上报上下文超出窗口时统一抛出的哨兵异常。"""


# ═══════════════════════════════════════════════════════════════════
# 消息角色常量
# ═══════════════════════════════════════════════════════════════════

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL = "tool"  # 携带工具执行结果的回合


# ═══════════════════════════════════════════════════════════════════
# 工具调用相关类型
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ToolCall:
    """协议无关地承载模型发起的一次工具调用（流式拼接完成后）。"""

    id: str
    name: str
    input: str


@dataclass
class ToolResult:
    """协议无关地承载一次工具执行结果。"""

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class ToolDefinition:
    """注册中心导出的协议无关工具定义。"""

    name: str
    description: str
    input_schema: dict[str, Any]


# ═══════════════════════════════════════════════════════════════════
# Token 用量
# ═══════════════════════════════════════════════════════════════════


@dataclass
class Usage:
    """一轮请求的 token 用量。"""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_write: int = 0  # Anthropic: cache_creation_input_tokens；OpenAI: 恒 0
    cache_read: int = 0  # Anthropic: cache_read_input_tokens；OpenAI: cached_tokens


# ═══════════════════════════════════════════════════════════════════
# 消息与事件
# ═══════════════════════════════════════════════════════════════════


@dataclass
class Message:
    """单条对话消息"""

    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass
class StreamEvent:
    """流式事件"""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None
    done: bool = False
    err: Exception | None = None


# ═══════════════════════════════════════════════════════════════════
# 请求结构
# ═══════════════════════════════════════════════════════════════════


@dataclass
class System:
    """系统提示两段：stable（可缓存） + environment（不缓存）。"""

    stable: str = ""
    environment: str = ""


@dataclass
class Request:
    """一次 LLM 请求的全部入参，由 Agent 组装、Provider 消费。"""

    messages: list[Message] = field(default_factory=list)
    tools: list[ToolDefinition] = field(default_factory=list)
    system: System = field(default_factory=System)
    reminder: str = ""  # 本轮 system-reminder 内容（已含标签；空=不注入）


# ═══════════════════════════════════════════════════════════════════
# Provider 接口
# ═══════════════════════════════════════════════════════════════════


class Provider(Protocol):
    """协议无关的 LLM 供应商接口"""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    def stream(self, req: Request) -> AsyncIterator[StreamEvent]:
        """发起一轮流式对话，由 Request 承载全部入参。"""
        ...


def new_provider(cfg: ProviderConfig) -> Provider:
    """按 protocol 构造对应的适配器"""
    if cfg.protocol == "anthropic":
        from micodeagent.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(cfg)
    elif cfg.protocol == "openai":
        from micodeagent.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(cfg)
    raise ValueError(f"不支持的协议: {cfg.protocol}")
