"""后台任务管理器"""

from __future__ import annotations

import asyncio
import secrets
import sys
import time
from dataclasses import dataclass, field
from enum import IntEnum


class Status(IntEnum):
    RUNNING = 0
    COMPLETED = 1
    FAILED = 2
    CANCELLED = 3


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0


@dataclass
class BackgroundTask:
    id: str
    name: str
    sub_agent: object
    conv: object
    task: str
    status: Status = Status.RUNNING
    result: str = ""
    err: Exception | None = None
    tool_count: int = 0
    last_activity: str = ""
    usage: Usage = field(default_factory=Usage)
    start_time: float = 0.0
    end_time: float = 0.0
    handle: asyncio.Task | None = None


class Manager:
    """后台子 Agent 任务管理器。"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._tasks: dict[str, BackgroundTask] = {}
        self._by_name: dict[str, str] = {}
        self._done: asyncio.Queue[str] = asyncio.Queue(maxsize=64)
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"task_{secrets.token_hex(4)}"

    def get(self, task_id: str) -> BackgroundTask | None:
        return self._tasks.get(task_id)

    def list(self) -> list[BackgroundTask]:
        return list(self._tasks.values())

    def subscribe_done(self) -> asyncio.Queue[str]:
        return self._done

    async def launch(self, ag, conv, name: str, task_text: str) -> str:
        task_id = self._next_id()
        bt = BackgroundTask(
            id=task_id,
            name=name,
            sub_agent=ag,
            conv=conv,
            task=task_text,
            status=Status.RUNNING,
            start_time=time.monotonic(),
        )
        async with self._lock:
            self._tasks[task_id] = bt
            if name:
                self._by_name[name] = task_id

        async def runner():
            try:
                text = await ag.run_to_completion(conv, task_text)
                bt.result = text
                bt.status = Status.COMPLETED
            except asyncio.CancelledError:
                bt.status = Status.CANCELLED
                raise
            except BaseException as e:
                bt.status = Status.FAILED
                bt.err = e
            finally:
                bt.end_time = time.monotonic()
                try:
                    self._done.put_nowait(task_id)
                except asyncio.QueueFull:
                    print(f"task manager: done queue full for {task_id}", file=sys.stderr)

        bt.handle = asyncio.create_task(runner())
        return task_id

    async def stop(self, task_id: str) -> bool:
        bt = self._tasks.get(task_id)
        if bt is None:
            return False
        if bt.handle is not None:
            bt.handle.cancel()
        return True

    async def send_message(self, name: str, message: str) -> str:
        task_id = self._by_name.get(name)
        if task_id is None:
            raise KeyError(f"unknown task: {name}")
        bt = self._tasks[task_id]
        if bt.status == Status.COMPLETED:
            bt.conv.add_user(message)
            bt.status = Status.RUNNING
            return await self.launch(bt.sub_agent, bt.conv, name, "")
        raise RuntimeError(f"task {name} is not completed")
