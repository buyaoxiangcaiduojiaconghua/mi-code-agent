"""子 Agent 目录：三层加载与解析"""

from __future__ import annotations

import sys
from pathlib import Path

from micodeagent.subagent.definition import Definition, Source
from micodeagent.subagent.embed import builtin_definitions
from micodeagent.subagent.parser import parse_file


class Catalog:
    """子 Agent 定义目录，同名高优先级覆盖。"""

    def __init__(self):
        self._by_name: dict[str, Definition] = {}
        self._by_source: dict[Source, list[Definition]] = {}

    def _add_all(self, defs: list[Definition], source: Source) -> None:
        for d in defs:
            self._by_name[d.name] = d
        self._by_source.setdefault(source, []).extend(defs)

    def resolve(self, name: str) -> Definition | None:
        return self._by_name.get(name)

    def list(self) -> list[Definition]:
        return sorted(self._by_name.values(), key=lambda d: d.name)

    def list_by_source(self, s: Source) -> list[Definition]:
        return list(self._by_source.get(s, []))

    def fork_definition(self) -> Definition:
        return Definition(name="__fork__", description="Fork-based subagent", max_turns=25)


def load_catalog(root: str) -> Catalog:
    """按 builtin → user → project 顺序加载。"""
    c = Catalog()
    c._add_all(builtin_definitions(), Source.BUILTIN)
    c._add_all(_load_from_dir(Path.home() / ".micodeagent" / "agents", Source.USER), Source.USER)
    c._add_all(
        _load_from_dir(Path(root) / ".micodeagent" / "agents", Source.PROJECT), Source.PROJECT
    )
    return c


def _load_from_dir(directory: Path, source: Source) -> list[Definition]:
    if not directory.is_dir():
        return []
    result = []
    for f in sorted(directory.glob("*.md")):
        try:
            result.append(parse_file(str(f), source))
        except (ValueError, OSError) as e:
            print(f"subagent: skip {f}: {e}", file=sys.stderr)
    return result
