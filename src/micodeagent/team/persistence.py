"""团队持久化：sanitize + 原子写"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


def sanitize(name: str) -> str:
    """只保留安全字符，其他替换为 -。"""
    result = re.sub(r"[^a-zA-Z0-9._-]", "-", name)
    result = result.strip("-")
    return result


def atomic_write_json(path: str | Path, value: Any) -> None:
    """原子写入 JSON。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def read_json(path: str | Path) -> Any:
    """读取 JSON，文件不存在抛 FileNotFoundError。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


async def reload_from_disk_locked(team) -> None:
    """持锁状态下从磁盘重载 members 字段。"""
    try:
        data = read_json(team.config_path)
        members_raw = data.get("members", [])
        from micodeagent.team.types import TeammateInfo

        team.members = [TeammateInfo(**m) for m in members_raw]
    except (FileNotFoundError, KeyError, TypeError):
        # 静默回退到内存现状
        pass
