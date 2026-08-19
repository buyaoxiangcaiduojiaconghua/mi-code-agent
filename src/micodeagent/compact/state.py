"""上下文管理状态对象

ContentReplacementState、CompactCircuitBreaker、RecoveryState、SessionContext。
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from micodeagent.compact.const import MAX_CONSECUTIVE_AUTO_COMPACT_FAILURES


class ContentReplacementState:
    """会话级的工具结果替换决策账本。

    _seen_ids 记录已经决策过的 tool_use_id，无论决策是替换还是保留原文。
    _replacements 只保存"决定替换"那一支的预览字符串。
    同一个 tool_use_id 一旦进入 _seen_ids 就再也不会被重新评估。
    """

    def __init__(self) -> None:
        self._seen_ids: set[str] = set()
        self._replacements: dict[str, str] = {}

    def decide_once(
        self,
        tool_use_id: str,
        original: str,
        decide: Callable[[], tuple[str, str]],
    ) -> str:
        """一次性完成"查账本→决策→写账本"原子操作。

        decide 回调返回 (decision, preview)，其中：
          - "kept" → 写 _seen_ids，不写 _replacements；返回原 content。
          - "replaced" → 写 _seen_ids + _replacements；返回 preview。
          - "skip" → 既不写 _seen_ids 也不写 _replacements；返回原 content。
        """
        if tool_use_id in self._seen_ids:
            return self._replacements.get(tool_use_id, original)

        decision, preview = decide()
        if decision == "kept":
            self._seen_ids.add(tool_use_id)
            return original
        elif decision == "replaced":
            self._seen_ids.add(tool_use_id)
            self._replacements[tool_use_id] = preview
            return preview
        else:  # skip
            return original


class CompactCircuitBreaker:
    """跟踪自动摘要连续失败次数，用于熔断。"""

    def __init__(self) -> None:
        self._consecutive_failures = 0

    def record_success(self) -> None:
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        self._consecutive_failures += 1

    def tripped(self) -> bool:
        return self._consecutive_failures >= MAX_CONSECUTIVE_AUTO_COMPACT_FAILURES


@dataclass
class FileReadRecord:
    """文件读取追踪记录。"""

    path: str
    content: str
    timestamp: datetime


class RecoveryState:
    """文件追踪状态，Agent 主循环写、compact 摘要时读。"""

    def __init__(self) -> None:
        self._files: dict[str, FileReadRecord] = {}

    def record_file(self, path: str, content: str) -> None:
        abs_path = str(Path(path).resolve())
        self._files[abs_path] = FileReadRecord(
            path=abs_path, content=content, timestamp=datetime.now()
        )

    def snapshot(self) -> list[FileReadRecord]:
        """返回按 timestamp 倒序排序的拷贝列表。"""
        records = list(self._files.values())
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records


@dataclass
class SessionContext:
    """会话生命周期信息。"""

    session_id: str
    spill_dir: str
    session_dir: str = ""


def _new_session_id() -> str:
    """生成 YYYYMMDD-HHMMSS-<4hex> 格式的会话 ID。"""
    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        hex_str = secrets.token_hex(2)
    except Exception:
        import logging
        import random

        logging.warning("secrets.token_hex failed, falling back to random")
        hex_str = random.Random(time.time()).randbytes(2).hex()
    return f"{ts}-{hex_str}"


def parse_session_time(session_id: str) -> "datetime | None":
    """从 session ID 前 15 位解析 YYYYMMDD-HHMMSS，失败返回 None。"""
    from datetime import datetime

    try:
        return datetime.strptime(session_id[:15], "%Y%m%d-%H%M%S")
    except (ValueError, IndexError):
        return None


def new_session_context(workspace: str) -> SessionContext:
    session_id = _new_session_id()
    session_dir = str(Path(workspace) / ".micodeagent" / "sessions" / session_id)
    spill_dir = str(Path(session_dir) / "tool-results")
    Path(spill_dir).mkdir(parents=True, exist_ok=True)
    return SessionContext(session_id=session_id, spill_dir=spill_dir, session_dir=session_dir)


def open_session_context(workspace: str, session_id: str) -> SessionContext:
    """打开已存在的会话目录，不创建。"""
    session_dir = str(Path(workspace) / ".micodeagent" / "sessions" / session_id)
    spill_dir = str(Path(session_dir) / "tool-results")
    return SessionContext(session_id=session_id, spill_dir=spill_dir, session_dir=session_dir)
