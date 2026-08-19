"""记忆管理器"""

from __future__ import annotations

import asyncio
import json
import logging

from micodeagent.llm import Message, Request
from micodeagent.memory.prompts import MEMORY_UPDATE_SYSTEM_PROMPT
from micodeagent.memory.store import Store
from micodeagent.memory.types import UpdateAction

logger = logging.getLogger(__name__)

INDEX_LIMIT = 25 * 1024  # 25KB


class Manager:
    """两级记忆管理器。"""

    def __init__(self, project_dir: str, user_dir: str, provider=None, model: str = ""):
        self.project_store = Store(project_dir)
        self.user_store = Store(user_dir)
        self._provider = provider
        self._model = model
        self._lock = asyncio.Lock()

    def set_provider(self, provider, model: str) -> None:
        self._provider = provider
        self._model = model

    def load_index(self) -> str:
        """合并两级索引，项目级在前。"""
        project = self.project_store.load_index()
        user = self.user_store.load_index()
        combined = (project + "\n" + user).strip()
        if len(combined.encode("utf-8")) > INDEX_LIMIT:
            truncated = combined.encode("utf-8")[:INDEX_LIMIT].decode("utf-8", errors="replace")
            return truncated + "\n(index truncated)"
        return combined

    def list_files(self) -> tuple[list[str], list[str]]:
        """列出项目层与用户层的 .md 文件（含 MEMORY.md）。"""
        return (self._list_dir(self.project_store._dir), self._list_dir(self.user_store._dir))

    @staticmethod
    def _list_dir(directory: str) -> list[str]:
        import os

        if not os.path.isdir(directory):
            return []
        try:
            files = sorted(f for f in os.listdir(directory) if f.endswith(".md"))
        except OSError as e:
            logger.warning("列出 memory 目录失败 %s: %s", directory, e)
            return []
        return files

    async def update_async(self, recent_msgs: list[Message]) -> None:
        """异步更新记忆。"""
        if self._provider is None:
            return
        try:
            async with self._lock:
                await self._update(recent_msgs)
        except Exception as e:
            logger.exception("记忆更新失败: %s", e)

    async def _update(self, recent_msgs: list[Message]) -> None:
        # 构造更新请求
        index = self.load_index()
        msgs_text = "\n".join(f"{m.role}: {m.content}" for m in recent_msgs)
        content = (
            MEMORY_UPDATE_SYSTEM_PROMPT
            + "\n\n[现有索引]\n"
            + (index or "(空)")
            + "\n\n[最近对话]\n"
            + msgs_text
        )
        req = Request(messages=[Message(role="user", content=content)], tools=[])

        text_buf = []
        async for ev in self._provider.stream(req):
            if ev.err is not None:
                return
            if ev.text:
                text_buf.append(ev.text)

        raw = "".join(text_buf).strip()
        actions = self._parse_actions(raw)
        for action in actions:
            self._apply_action(action)

    @staticmethod
    def _parse_actions(raw: str) -> list[UpdateAction]:
        """解析 LLM 返回的 JSON 数组。"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # 尝试提取 JSON 数组
            start = raw.find("[")
            end = raw.rfind("]")
            if start == -1 or end == -1:
                return []
            try:
                data = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return []

        if not isinstance(data, list):
            return []
        actions = []
        for item in data:
            if not isinstance(item, dict):
                continue
            actions.append(
                UpdateAction(
                    action=item.get("action", ""),
                    level=item.get("level", "project"),
                    type=item.get("type", ""),
                    title=item.get("title", ""),
                    slug=item.get("slug", ""),
                    filename=item.get("filename", ""),
                    content=item.get("content", ""),
                )
            )
        return actions

    def _apply_action(self, action: UpdateAction) -> None:
        """按 level 分发到对应 store。"""
        store = self.project_store if action.level == "project" else self.user_store
        store.apply([action])
