"""内置子 Agent 定义加载"""

from __future__ import annotations

from importlib.resources import files

from micodeagent.subagent.definition import Definition, Source
from micodeagent.subagent.parser import parse_definition


def builtin_definitions() -> list[Definition]:
    """加载内置子 Agent 定义。"""
    pkg = files("micodeagent.subagent.builtin")
    result = []
    for name in sorted(pkg.iterdir()):
        if not str(name).endswith(".md"):
            continue
        data = (pkg / name).read_bytes()
        result.append(parse_definition(data, f"builtin:{name}", Source.BUILTIN))
    result.sort(key=lambda d: d.name)
    return result
