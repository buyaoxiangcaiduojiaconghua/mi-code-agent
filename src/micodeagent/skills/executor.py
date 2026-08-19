"""Skill 执行器：inline 与 fork 两种模式"""

from __future__ import annotations

from micodeagent.skills.parser import SkillDef, substitute_arguments


class SkillExecutor:
    """执行 skill 的两种模式。"""

    def __init__(self, agent=None, client=None, protocol=None):
        self._agent = agent
        self._client = client
        self._protocol = protocol

    def execute_inline(self, skill: SkillDef, args: str) -> None:
        """inline 模式：渲染 SOP 并钉到环境上下文。"""
        rendered = substitute_arguments(skill.prompt_body, args)
        if self._agent is not None:
            self._agent.activate_skill(skill.name, rendered)

    async def execute_fork(self, skill: SkillDef, args: str) -> str:
        """fork 模式：独立对话执行，返回结果文本。"""
        rendered = substitute_arguments(skill.prompt_body, args)
        # fork 模式目前返回渲染结果，完整独立对话留待 SubAgent 章节
        return rendered
