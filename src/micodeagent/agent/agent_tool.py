"""Agent 工具：委派子 Agent"""

from __future__ import annotations

import json

from micodeagent.agent.fork import build_forked_messages
from micodeagent.conversation import Conversation
from micodeagent.tool import Result


class AgentTool:
    """统一的子 Agent 委派工具。"""

    read_only = False

    def __init__(self, catalog, parent=None, bg_enabled: bool = True):
        self._catalog = catalog
        self._parent = parent
        self._bg_enabled = bg_enabled

    def set_parent(self, parent) -> None:
        self._parent = parent

    def name(self) -> str:
        return "agent"

    def description(self) -> str:
        types = ", ".join(d.name for d in self._catalog.list())
        return (
            "委派一个子任务给子 Agent，返回其执行结果。"
            f"subagent_type 可选值: {types}。"
            "不传 subagent_type 时使用 Fork 模式（继承当前对话上下文）。"
        )

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "子任务描述"},
                "description": {"type": "string", "description": "子任务简短说明"},
                "subagent_type": {"type": "string", "description": "子 Agent 类型名，可选"},
            },
            "required": ["prompt", "description"],
        }

    async def execute(self, args: str) -> Result:
        if self._parent is None:
            return Result(content="Agent 工具未正确初始化", is_error=True)
        try:
            data = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            return Result(content="参数 JSON 解析失败", is_error=True)

        prompt = data.get("prompt", "")
        description = data.get("description", "")
        if not prompt:
            return Result(content="prompt is required", is_error=True)
        if not description:
            return Result(content="description is required", is_error=True)

        subagent_type = data.get("subagent_type", "")
        if subagent_type:
            definition = self._catalog.resolve(subagent_type)
            if definition is None:
                return Result(content=f"unknown subagent_type: {subagent_type}", is_error=True)
        else:
            definition = self._catalog.fork_definition()

        # 构造子 Agent
        from micodeagent.agent import Agent

        sub_agent = Agent(
            provider=self._parent._provider,
            registry=self._parent._registry,
            version=self._parent._version,
            engine=self._parent._engine,
            runtime=self._parent.runtime,
            memory_manager=None,
            instruction_text=definition.system_prompt,
            memory_text="",
            hook_engine=self._parent._hook_engine,
        )

        # 子对话
        if definition.is_fork():
            # Fork 模式：继承父历史（此处用空历史，完整继承由上层传 context）
            forked = build_forked_messages([], prompt)
            sub_conv = Conversation.from_messages(forked)
            final_text = await sub_agent.run_to_completion(sub_conv, "")
        else:
            sub_conv = Conversation()
            final_text = await sub_agent.run_to_completion(sub_conv, prompt)

        return Result(content=final_text)
