"""命令注册中心"""

from __future__ import annotations

from micodeagent.command.command import Command


class Registry:
    """命令注册中心，含冲突检测与前缀匹配。"""

    def __init__(self) -> None:
        self._by_name: dict[str, Command] = {}
        self._visible: list[Command] = []

    def register(self, cmd: Command) -> None:
        """注册命令，别名冲突时抛 RuntimeError。"""
        if not cmd.name or cmd.name != cmd.name.lower():
            raise RuntimeError(f"command name must be non-empty lowercase: {cmd.name!r}")
        for alias in cmd.aliases:
            if not alias or alias != alias.lower():
                raise RuntimeError(f"alias must be non-empty lowercase: {alias!r}")

        for key in (cmd.name, *cmd.aliases):
            if key in self._by_name:
                raise RuntimeError(f"command conflict: {key}")

        for key in (cmd.name, *cmd.aliases):
            self._by_name[key] = cmd

        if not cmd.hidden:
            self._visible.append(cmd)
            self._visible.sort(key=lambda c: c.name)

    def lookup(self, name: str) -> Command | None:
        """按名查找（大小写不敏感）。"""
        return self._by_name.get(name.lower())

    def visible(self) -> list[Command]:
        """返回可见命令列表副本。"""
        return list(self._visible)

    def prefix_match(self, prefix: str) -> list[Command]:
        """前缀匹配可见命令。"""
        p = prefix.lstrip("/").lower()
        if p == "":
            return list(self._visible)
        return [c for c in self._visible if c.name.startswith(p)]
