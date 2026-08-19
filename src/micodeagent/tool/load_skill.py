"""LoadSkill 工具——按需激活 skill"""

from __future__ import annotations

import json

from micodeagent.tool import Result


class LoadSkillTool:
    """按需加载并激活一个 skill。"""

    read_only = True

    def __init__(self):
        self._loader = None
        self._agent = None

    def set_loader(self, loader) -> None:
        self._loader = loader

    def set_agent(self, agent) -> None:
        self._agent = agent

    def name(self) -> str:
        return "load_skill"

    def description(self) -> str:
        return (
            "按需激活一个 Skill。"
            "当用户的请求匹配某个 Skill 时，调用此工具传入 Skill 名称，"
            "将其完整 SOP 指令加载到环境上下文。"
        )

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "要激活的 Skill 名称"},
            },
            "required": ["name"],
        }

    async def execute(self, args: str) -> Result:
        if self._loader is None or self._agent is None:
            return Result(content="LoadSkill 未正确初始化", is_error=True)
        try:
            data = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            return Result(content="参数 JSON 解析失败", is_error=True)

        name = data.get("name", "")
        skill = self._loader.get(name)
        if skill is None:
            catalog = ", ".join(n for n, _ in self._loader.get_catalog())
            return Result(content=f"未知 Skill: {name}，可用: {catalog}", is_error=True)

        self._agent.activate_skill(skill.name, skill.prompt_body)
        return Result(content=f"Skill '{name}' 已激活，SOP 已钉到环境上下文。")
