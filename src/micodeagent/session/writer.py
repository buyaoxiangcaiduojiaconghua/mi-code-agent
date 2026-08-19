"""会话 JSONL 写入器"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass

from micodeagent.llm import Message


@dataclass
class Entry:
    """单条 JSONL 记录。"""

    role: str
    ts: int
    content: str = ""
    tool_calls: list | None = None
    tool_results: list | None = None
    model: str = ""

    def to_dict(self) -> dict:
        d = {"role": self.role, "ts": self.ts}
        if self.content:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_results:
            d["tool_results"] = self.tool_results
        if self.model:
            d["model"] = self.model
        return d


class Writer:
    """会话 JSONL 追加写入器。"""

    def __init__(self, session_dir: str):
        os.makedirs(session_dir, exist_ok=True)
        self._path = os.path.join(session_dir, "conversation.jsonl")
        self.path = os.path.abspath(self._path)
        self._file = open(self._path, "ab")
        self._lock = threading.Lock()
        self._first = True

    @classmethod
    def open_existing(cls, session_dir: str) -> "Writer":
        """打开已存在会话目录（追加模式）。"""
        w = cls.__new__(cls)
        w._path = os.path.join(session_dir, "conversation.jsonl")
        w.path = os.path.abspath(w._path)
        w._file = open(w._path, "ab")
        w._lock = threading.Lock()
        w._first = not os.path.exists(w._path) or os.path.getsize(w._path) == 0
        return w

    @classmethod
    def open_writer(cls, session_dir: str) -> "Writer":
        """打开会话目录（追加模式），别名。"""
        return cls.open_existing(session_dir)

    def append(self, msg: Message, model: str = "", is_first: bool = False) -> None:
        """追加一条消息。"""
        entry = Entry(role=msg.role, content=msg.content, ts=int(time.time()))
        if msg.tool_calls:
            entry.tool_calls = [
                {"id": c.id, "name": c.name, "input": c.input} for c in msg.tool_calls
            ]
        if msg.tool_results:
            entry.tool_results = [
                {"tool_call_id": r.tool_call_id, "content": r.content, "is_error": r.is_error}
                for r in msg.tool_results
            ]
        if is_first and model:
            entry.model = model

        line = json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"
        with self._lock:
            self._file.write(line.encode("utf-8"))
            self._file.flush()
            os.fsync(self._file.fileno())

    def write_compact_marker(self) -> None:
        """写入压缩标记行。"""
        line = json.dumps({"type": "compact", "ts": int(time.time())}) + "\n"
        with self._lock:
            self._file.write(line.encode("utf-8"))
            self._file.flush()
            os.fsync(self._file.fileno())

    def append_all(self, msgs: list[Message]) -> None:
        """逐条追加消息列表。"""
        for msg in msgs:
            self.append(msg)

    def on_append(self, msg: Message) -> None:
        """Conversation 回调：追加消息。"""
        self.append(msg)

    def on_replace(self, msgs: list[Message]) -> None:
        """Conversation 回调：压缩后整体替换。"""
        self.write_compact_marker()
        self.append_all(msgs)

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "Writer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
