"""记忆存储：笔记文件 CRUD + 索引读写"""

from __future__ import annotations

import os
import threading
from datetime import datetime

from micodeagent.memory.types import UpdateAction

INDEX_NAME = "MEMORY.md"


class Store:
    """单级记忆目录的存储。"""

    def __init__(self, directory: str):
        self._dir = directory
        self._lock = threading.Lock()

    def ensure_dir(self) -> None:
        os.makedirs(self._dir, exist_ok=True)

    def load_index(self) -> str:
        """读取索引文件内容。"""
        path = os.path.join(self._dir, INDEX_NAME)
        if not os.path.exists(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def apply(self, actions: list[UpdateAction]) -> None:
        """执行记忆更新操作。"""
        with self._lock:
            self.ensure_dir()
            for action in actions:
                if action.action == "create":
                    self._create(action)
                elif action.action == "update":
                    self._update(action)
                elif action.action == "delete":
                    self._delete(action)

    def _create(self, action: UpdateAction) -> None:
        filename = action.filename or f"{action.type}_{action.slug}.md"
        path = os.path.join(self._dir, filename)
        now = datetime.now().isoformat()
        frontmatter = (
            f"---\ntype: {action.type}\ntitle: {action.title}\n"
            f"created: {now}\nupdated: {now}\n---\n"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(frontmatter + action.content + "\n")
        self._append_index(action.type, action.title, action.content)

    def _update(self, action: UpdateAction) -> None:
        filename = action.filename
        path = os.path.join(self._dir, filename)
        now = datetime.now().isoformat()
        # 保留 created，更新 updated
        old_content = ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                old_content = f.read()
        except OSError:
            pass

        created = now
        for line in old_content.split("\n"):
            if line.startswith("created:"):
                created = line.split(":", 1)[1].strip()

        frontmatter = (
            f"---\ntype: {action.type}\ntitle: {action.title}\n"
            f"created: {created}\nupdated: {now}\n---\n"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(frontmatter + action.content + "\n")
        self._update_index_line(filename, action.type, action.title, action.content)

    def _delete(self, action: UpdateAction) -> None:
        filename = action.filename
        path = os.path.join(self._dir, filename)
        try:
            os.remove(path)
        except OSError:
            pass
        self._remove_index_line(filename)

    def _append_index(self, note_type: str, title: str, content: str) -> None:
        line = f"- [{note_type}] {title} — {content[:50]}\n"
        path = os.path.join(self._dir, INDEX_NAME)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)

    def _update_index_line(self, filename: str, note_type: str, title: str, content: str) -> None:
        path = os.path.join(self._dir, INDEX_NAME)
        lines = self._read_index_lines(path)
        # 简单策略：按 title 匹配更新对应行
        new_line = f"- [{note_type}] {title} — {content[:50]}"
        found = False
        for i, line in enumerate(lines):
            if f"] {title} " in line or f"] {title} —" in line:
                lines[i] = new_line
                found = True
                break
        if not found:
            lines.append(new_line)
        self._write_index_lines(path, lines)

    def _remove_index_line(self, filename: str) -> None:
        path = os.path.join(self._dir, INDEX_NAME)
        lines = self._read_index_lines(path)
        lines = [ln for ln in lines if filename not in ln]
        self._write_index_lines(path, lines)

    @staticmethod
    def _read_index_lines(path: str) -> list[str]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().splitlines()
        except OSError:
            return []

    @staticmethod
    def _write_index_lines(path: str, lines: list[str]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
