"""会话列表扫描"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from micodeagent.compact.state import parse_session_time


@dataclass
class SessionInfo:
    """单个会话的元信息。"""

    id: str
    dir: str
    title: str
    model: str
    size: int
    modified_at: float


def list_sessions(sessions_dir: str) -> list[SessionInfo]:
    """扫描会话目录，返回按修改时间倒序的会话列表。"""
    base = Path(sessions_dir)
    if not base.exists():
        return []

    infos = []
    for sub in base.iterdir():
        if not sub.is_dir():
            continue
        # 解析时间戳，旧格式跳过
        if parse_session_time(sub.name) is None:
            continue

        jsonl = sub / "conversation.jsonl"
        if not jsonl.exists():
            continue

        title = ""
        model = ""
        try:
            with open(jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("role") == "user":
                        title = data.get("content", "")[:50]
                        model = data.get("model", "")
                        break
        except OSError:
            continue

        st = jsonl.stat()
        infos.append(
            SessionInfo(
                id=sub.name,
                dir=str(sub),
                title=title or "(空会话)",
                model=model,
                size=st.st_size,
                modified_at=st.st_mtime,
            )
        )

    infos.sort(key=lambda i: i.modified_at, reverse=True)
    return infos
