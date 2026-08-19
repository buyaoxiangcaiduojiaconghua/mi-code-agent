"""Hook 条件求值"""

from __future__ import annotations

import json
from typing import Any

from micodeagent.hook.rule import CombineMode, Condition, Payload


def get_by_path(p: Payload, path: str) -> str:
    """按 . 分隔路径取值，非字符串时转字符串。"""
    cur: Any = p
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return ""
        cur = cur[part]
        if cur is None:
            return ""
    if isinstance(cur, bool):
        return "True" if cur else "False"
    if isinstance(cur, (int, float)):
        return str(cur)
    if isinstance(cur, str):
        return cur
    return json.dumps(cur, sort_keys=True)


def eval_condition(c: Condition | None, p: Payload) -> bool:
    """求值条件；c 为 None 表示无条件。"""
    if c is None:
        return True
    results = [atom.matcher.match(get_by_path(p, atom.field)) for atom in c.atoms]
    if c.combine == CombineMode.ALL_OF:
        return all(results)
    return any(results)
