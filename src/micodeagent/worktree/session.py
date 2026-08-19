"""Worktree 会话持久化"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class WorktreeSession:
    worktree_name: str
    worktree_path: str
    original_cwd: str
    original_branch: str
    original_head: str
    session_id: str


def load_session(path: Path) -> WorktreeSession | None:
    """加载会话文件；不存在或空返回 None。"""
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw or raw == "null":
        return None
    data = json.loads(raw)
    return WorktreeSession(**data)


def save_session(path: Path, session: WorktreeSession | None) -> None:
    """原子写入会话；None 写 null。"""
    content = "null" if session is None else json.dumps(asdict(session), ensure_ascii=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def clear_session(path: Path) -> None:
    save_session(path, None)
