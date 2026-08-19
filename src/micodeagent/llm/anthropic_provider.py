"""Anthropic 适配器

封装 `anthropic.AsyncAnthropic`，支持流式对话、工具定义注入、
流式工具调用解析、工具结果回灌、缓存断点与 token 用量上抛。
"""

import asyncio
import json
from collections.abc import AsyncIterator

import anthropic

from micodeagent.config import ProviderConfig
from micodeagent.llm import (
    ROLE_ASSISTANT,
    ROLE_TOOL,
    ROLE_USER,
    Message,
    PromptTooLongError,
    Request,
    StreamEvent,
    ToolCall,
    ToolDefinition,
    Usage,
)


class AnthropicProvider:
    """Anthropic Claude API 的 Provider 实现"""

    def __init__(self, cfg: ProviderConfig):
        self._cfg = cfg
        self._client = anthropic.AsyncAnthropic(
            api_key=cfg.api_key,
            base_url=cfg.base_url or None,
        )

    @property
    def name(self) -> str:
        return self._cfg.name

    @property
    def model(self) -> str:
        return self._cfg.model

    async def stream(self, req: Request) -> AsyncIterator[StreamEvent]:
        """流式对话，由 Request 承载全部入参。"""
        # 构造 system 块列表
        system_blocks: list[dict] = []
        if req.system.stable:
            system_blocks.append(
                {
                    "type": "text",
                    "text": req.system.stable,
                    "cache_control": {"type": "ephemeral"},
                }
            )
        if req.system.environment:
            system_blocks.append({"type": "text", "text": req.system.environment})

        messages = self._to_anthropic_messages(req.messages)

        # reminder 织入末条 user 消息
        if req.reminder:
            _append_reminder_anthropic(messages, req.reminder)

        params: dict = {
            "model": self._cfg.model,
            "max_tokens": 4096,
            "system": system_blocks,
            "messages": messages,
        }

        if req.tools:
            params["tools"] = self._to_anthropic_tools(req.tools)

        if self._cfg.thinking and not self._has_tool_history(req.messages):
            params["thinking"] = {"type": "enabled", "budget_tokens": 2048}

        try:
            async with self._client.messages.stream(**params) as stream:
                async for event in stream:
                    if event.type == "text":
                        yield StreamEvent(text=event.text)

            final_message = await stream.get_final_message()
            if final_message:
                if final_message.usage:
                    yield StreamEvent(
                        usage=Usage(
                            input_tokens=final_message.usage.input_tokens or 0,
                            output_tokens=final_message.usage.output_tokens or 0,
                            cache_write=getattr(
                                final_message.usage, "cache_creation_input_tokens", 0
                            )
                            or 0,
                            cache_read=getattr(final_message.usage, "cache_read_input_tokens", 0)
                            or 0,
                        )
                    )
                if final_message.stop_reason == "tool_use":
                    calls = []
                    for block in final_message.content:
                        if block.type == "tool_use":
                            calls.append(
                                ToolCall(
                                    id=block.id,
                                    name=block.name,
                                    input=json.dumps(block.input),
                                )
                            )
                    if calls:
                        yield StreamEvent(tool_calls=calls)

            yield StreamEvent(done=True)
        except asyncio.CancelledError:
            raise
        except anthropic.BadRequestError as e:
            msg = str(e).lower()
            if "prompt is too long" in msg or "context_length" in msg or "context length" in msg:
                wrapped = PromptTooLongError("anthropic prompt too long")
                wrapped.__cause__ = e
                yield StreamEvent(err=wrapped)
            else:
                yield StreamEvent(err=e)
        except Exception as e:
            yield StreamEvent(err=e)

    # ---- 消息转换 ----

    @staticmethod
    def _to_anthropic_messages(msgs: list[Message]) -> list[dict]:
        result = []
        for m in msgs:
            if m.role == ROLE_USER:
                result.append({"role": "user", "content": [{"type": "text", "text": m.content}]})
            elif m.role == ROLE_ASSISTANT:
                if m.tool_calls:
                    content = []
                    if m.content:
                        content.append({"type": "text", "text": m.content})
                    for c in m.tool_calls:
                        content.append(
                            {
                                "type": "tool_use",
                                "id": c.id,
                                "name": c.name,
                                "input": json.loads(c.input),
                            }
                        )
                    result.append({"role": "assistant", "content": content})
                else:
                    result.append(
                        {"role": "assistant", "content": [{"type": "text", "text": m.content}]}
                    )
            elif m.role == ROLE_TOOL:
                content = []
                for r in m.tool_results:
                    content.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": r.tool_call_id,
                            "content": r.content,
                            "is_error": r.is_error,
                        }
                    )
                result.append({"role": "user", "content": content})
        return result

    @staticmethod
    def _to_anthropic_tools(tools: list[ToolDefinition]) -> list[dict]:
        return [
            {"name": d.name, "description": d.description, "input_schema": d.input_schema}
            for d in tools
        ]

    @staticmethod
    def _has_tool_history(msgs: list[Message]) -> bool:
        for m in msgs:
            if m.tool_calls or m.tool_results:
                return True
        return False


def _append_reminder_anthropic(messages: list[dict], reminder: str) -> None:
    """把 reminder 文本块追加到最后一条消息的 content 中。"""
    if not messages:
        messages.append({"role": "user", "content": [{"type": "text", "text": reminder}]})
        return

    last = messages[-1]
    if last["role"] == "user":
        content = last["content"]
        if isinstance(content, list):
            content.append({"type": "text", "text": reminder})
        else:
            last["content"] = [
                {"type": "text", "text": content},
                {"type": "text", "text": reminder},
            ]
    else:
        messages.append({"role": "user", "content": [{"type": "text", "text": reminder}]})
