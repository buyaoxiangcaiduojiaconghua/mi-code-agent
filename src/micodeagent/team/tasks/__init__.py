"""团队共享任务存储"""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from enum import Enum

from micodeagent.team.persistence import atomic_write_json, read_json


class Status(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class Task:
    id: str = ""
    title: str = ""
    description: str = ""
    status: str = "todo"
    assignee: str = ""
    blocks: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "assignee": self.assignee,
            "blocks": self.blocks,
            "blocked_by": self.blocked_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(
            id=d.get("id", ""),
            title=d.get("title", ""),
            description=d.get("description", ""),
            status=d.get("status", "todo"),
            assignee=d.get("assignee", ""),
            blocks=d.get("blocks", []),
            blocked_by=d.get("blocked_by", []),
        )


@dataclass
class Filter:
    status: str = ""


@dataclass
class Patch:
    title: str = ""
    description: str = ""
    status: str = ""
    assignee: str = ""
    add_blocks: list[str] = field(default_factory=list)
    add_blocked_by: list[str] = field(default_factory=list)
    remove_blocks: list[str] = field(default_factory=list)
    remove_blocked_by: list[str] = field(default_factory=list)


class Store:
    """团队共享任务清单。"""

    def __init__(self, path: str):
        self._path = path
        self._lock = asyncio.Lock()

    async def _all(self) -> list[Task]:
        try:
            return [Task.from_dict(d) for d in read_json(self._path)]
        except FileNotFoundError:
            return []

    async def create(self, t: Task) -> str:
        async with self._lock:
            tasks = await self._all()
            t.id = "task_" + secrets.token_hex(3)
            tasks.append(t)
            atomic_write_json(self._path, [x.to_dict() for x in tasks])
            return t.id

    async def get(self, id_: str) -> Task | None:
        for t in await self._all():
            if t.id == id_:
                return t
        return None

    async def list_(self, f: Filter) -> list[Task]:
        tasks = await self._all()
        if f.status:
            tasks = [t for t in tasks if t.status == f.status]
        # 计算 is_ready
        all_by_id = {t.id: t for t in await self._all()}
        for t in tasks:
            ready = all(
                all_by_id.get(b) is not None and all_by_id[b].status == "done" for b in t.blocked_by
            )
            setattr(t, "is_ready", ready)
        return tasks

    async def update(self, id_: str, p: Patch) -> None:
        async with self._lock:
            tasks = await self._all()
            for t in tasks:
                if t.id == id_:
                    if p.title:
                        t.title = p.title
                    if p.description:
                        t.description = p.description
                    if p.status:
                        t.status = p.status
                    if p.assignee:
                        t.assignee = p.assignee
                    for b in p.add_blocks:
                        if b not in t.blocks:
                            t.blocks.append(b)
                    for b in p.remove_blocks:
                        if b in t.blocks:
                            t.blocks.remove(b)
                    for b in p.add_blocked_by:
                        if b not in t.blocked_by:
                            t.blocked_by.append(b)
                        # 双向维护
                        for other in tasks:
                            if other.id == b and id_ not in other.blocks:
                                other.blocks.append(id_)
                    for b in p.remove_blocked_by:
                        if b in t.blocked_by:
                            t.blocked_by.remove(b)
            atomic_write_json(self._path, [x.to_dict() for x in tasks])
