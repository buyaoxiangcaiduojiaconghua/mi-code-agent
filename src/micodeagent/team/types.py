"""团队基础类型"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum


class BackendType(str, Enum):
    TMUX = "tmux"
    ITERM2 = "iterm2"
    IN_PROCESS = "in_process"


class TeamError(Exception):
    """团队错误基类"""


class TeamNotFoundError(TeamError):
    pass


class TeamHasActiveMembersError(TeamError):
    pass


class MemberExistsError(TeamError):
    pass


class MemberNotFoundError(TeamError):
    pass


class InProcessTeammateNoSpawnError(TeamError):
    pass


@dataclass
class TeammateInfo:
    """队员信息。"""

    name: str
    agent_id: str = ""
    agent_type: str = "general-purpose"
    model: str = ""
    worktree: str = ""
    backend_type: str = "in_process"
    pane_id: str = ""
    session_dir: str = ""
    is_active: bool = False
    needs_approval: bool = False


@dataclass
class Team:
    """长期小组对象。"""

    name: str
    sanitized_name: str = ""
    lead_agent_id: str = ""
    backend: str = "in_process"
    description: str = ""
    created_at: str = ""
    members: list[TeammateInfo] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    # 派生路径（序列化时跳过）
    config_dir: str = field(default="", repr=False)
    config_path: str = field(default="", repr=False)
    tasks_path: str = field(default="", repr=False)
    mailbox_dir: str = field(default="", repr=False)

    def member_by_name(self, name: str) -> TeammateInfo | None:
        for m in self.members:
            if m.name == name:
                return m
        return None

    def member_by_agent_id(self, agent_id: str) -> TeammateInfo | None:
        for m in self.members:
            if m.agent_id == agent_id:
                return m
        return None
