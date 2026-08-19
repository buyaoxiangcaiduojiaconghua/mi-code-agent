"""团队邮箱：消息类型与读写"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from micodeagent.team.filelock import acquire
from micodeagent.team.persistence import atomic_write_json, read_json


class MessageType(str, Enum):
    TEXT = "text"
    PLAN_APPROVAL_REQUEST = "plan_approval_request"
    PLAN_APPROVAL_RESPONSE = "plan_approval_response"
    SHUTDOWN_REQUEST = "shutdown_request"
    IDLE = "idle"


@dataclass
class Message:
    from_: str
    text: str = ""
    type: str = "text"
    timestamp: str = ""
    read: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["from"] = d.pop("from_")
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        return cls(
            from_=d.get("from", ""),
            text=d.get("text", ""),
            type=d.get("type", "text"),
            timestamp=d.get("timestamp", ""),
            read=d.get("read", False),
        )


class Box:
    """单成员邮箱文件。"""

    def __init__(self, dir_: str):
        self._dir = dir_
        Path(dir_).mkdir(parents=True, exist_ok=True)

    def _path(self, agent_id: str) -> str:
        return str(Path(self._dir) / f"{agent_id}.json")

    async def write(self, agent_id: str, msg: Message) -> None:
        lock_path = str(Path(self._dir) / f"{agent_id}.lock")
        async with acquire(lock_path):
            path = self._path(agent_id)
            try:
                msgs = [Message.from_dict(d) for d in read_json(path)]
            except FileNotFoundError:
                msgs = []
            if not msg.timestamp:
                msg.timestamp = datetime.now(timezone.utc).isoformat()
            msgs.append(msg)
            atomic_write_json(path, [m.to_dict() for m in msgs])

    async def read(self, agent_id: str) -> list[Message]:
        try:
            return [Message.from_dict(d) for d in read_json(self._path(agent_id))]
        except FileNotFoundError:
            return []

    async def read_unread(self, agent_id: str) -> tuple[list[int], list[Message]]:
        msgs = await self.read(agent_id)
        indices = [i for i, m in enumerate(msgs) if not m.read]
        return indices, [msgs[i] for i in indices]

    async def mark_read(self, agent_id: str, indices: list[int]) -> None:
        if not indices:
            return
        lock_path = str(Path(self._dir) / f"{agent_id}.lock")
        async with acquire(lock_path):
            path = self._path(agent_id)
            msgs = await self.read(agent_id)
            for i in indices:
                if 0 <= i < len(msgs):
                    msgs[i].read = True
            atomic_write_json(path, [m.to_dict() for m in msgs])
