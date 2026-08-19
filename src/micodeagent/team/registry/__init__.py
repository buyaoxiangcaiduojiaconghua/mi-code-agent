"""Agent 名称注册表"""

from __future__ import annotations


class AgentNameRegistry:
    """名称 ↔ agent_id 双向映射。"""

    def __init__(self):
        self._by_name: dict[str, str] = {}
        self._by_id: dict[str, str] = {}

    def register(self, name: str, agent_id: str) -> None:
        old = self._by_name.get(name)
        if old is not None:
            self._by_id.pop(old, None)
        self._by_name[name] = agent_id
        self._by_id[agent_id] = name

    def unregister(self, name: str) -> None:
        agent_id = self._by_name.pop(name, None)
        if agent_id is not None:
            self._by_id.pop(agent_id, None)

    def unregister_by_agent_id(self, agent_id: str) -> None:
        name = self._by_id.pop(agent_id, None)
        if name is not None:
            self._by_name.pop(name, None)

    def resolve(self, name_or_id: str) -> str | None:
        if name_or_id in self._by_name:
            return self._by_name[name_or_id]
        if name_or_id in self._by_id:
            return name_or_id
        return None

    def name_of(self, agent_id: str) -> str | None:
        return self._by_id.get(agent_id)

    def list_(self) -> dict[str, str]:
        return dict(self._by_name)
