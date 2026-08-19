"""OpenAI 适配器

封装 `openai.AsyncOpenAI`，支持流式对话、工具定义注入、
流式工具调用解析、工具结果回灌与 token 用量上抛。
"""

import asyncio
from collections.abc import AsyncIterator

import openai

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


class OpenAIProvider:
    """OpenAI 兼容 API 的 Provider 实现"""

    def __init__(self, cfg: ProviderConfig):
        self._cfg = cfg
        self._client = openai.AsyncOpenAI(
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
        # 系统消息：stable + env 拼接为单条
        system_content = req.system.stable
        if req.system.environment:
            system_content = system_content + "\n\n" + req.system.environment

        messages = [{"role": "system", "content": system_content}] + self._to_openai_messages(
            req.messages
        )

        # reminder 追加为尾部 user 消息
        if req.reminder:
            messages.append({"role": "user", "content": req.reminder})

        params: dict = {
            "model": self._cfg.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if req.tools:
            params["tools"] = self._to_openai_tools(req.tools)

        try:
            tool_calls_buf: dict[int, dict] = {}

            stream = await self._client.chat.completions.create(**params)
            async for chunk in stream:
                if not chunk.choices:
                    if chunk.usage:
                        cache_read = (
                            getattr(
                                getattr(chunk.usage, "prompt_tokens_details", None),
                                "cached_tokens",
                                0,
                            )
                            or 0
                        )
                        yield StreamEvent(
                            usage=Usage(
                                input_tokens=chunk.usage.prompt_tokens or 0,
                                output_tokens=chunk.usage.completion_tokens or 0,
                                cache_read=cache_read,
                            )
                        )
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                if delta and delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_buf:
                            tool_calls_buf[idx] = {"id": "", "name": "", "args": ""}
                        buf = tool_calls_buf[idx]
                        if tc_delta.id:
                            buf["id"] = tc_delta.id
                        if tc_delta.function and tc_delta.function.name:
                            buf["name"] += tc_delta.function.name
                        if tc_delta.function and tc_delta.function.arguments:
                            buf["args"] += tc_delta.function.arguments

                if delta and delta.content:
                    yield StreamEvent(text=delta.content)

            if tool_calls_buf:
                calls = []
                for idx in sorted(tool_calls_buf.keys()):
                    buf = tool_calls_buf[idx]
                    calls.append(
                        ToolCall(
                            id=buf["id"] or f"call_{idx}",
                            name=buf["name"],
                            input=buf["args"] or "{}",
                        )
                    )
                yield StreamEvent(tool_calls=calls)

            yield StreamEvent(done=True)
        except asyncio.CancelledError:
            raise
        except openai.BadRequestError as e:
            code = getattr(e, "code", "") or ""
            if code == "context_length_exceeded":
                wrapped = PromptTooLongError("openai context length exceeded")
                wrapped.__cause__ = e
                yield StreamEvent(err=wrapped)
            else:
                yield StreamEvent(err=e)
        except Exception as e:
            yield StreamEvent(err=e)

    # ---- 消息转换 ----

    @staticmethod
    def _to_openai_messages(msgs: list[Message]) -> list[dict]:
        result = []
        for m in msgs:
            if m.role == ROLE_USER:
                result.append({"role": "user", "content": m.content})
            elif m.role == ROLE_ASSISTANT:
                if m.tool_calls:
                    result.append(
                        {
                            "role": "assistant",
                            "content": m.content or None,
                            "tool_calls": [
                                {
                                    "id": c.id,
                                    "type": "function",
                                    "function": {
                                        "name": c.name,
                                        "arguments": c.input or "{}",
                                    },
                                }
                                for c in m.tool_calls
                            ],
                        }
                    )
                else:
                    result.append({"role": "assistant", "content": m.content})
            elif m.role == ROLE_TOOL:
                for r in m.tool_results:
                    result.append(
                        {"role": "tool", "tool_call_id": r.tool_call_id, "content": r.content}
                    )
        return result

    @staticmethod
    def _to_openai_tools(tools: list[ToolDefinition]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": d.name,
                    "description": d.description,
                    "parameters": d.input_schema,
                },
            }
            for d in tools
        ]
