"""Hook 规则数据结构"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from micodeagent.hook.event import Event
from micodeagent.permission.matcher import Matcher

# 通用 payload 类型
Payload = dict[str, Any]


class CombineMode(Enum):
    ALL_OF = "all_of"
    ANY_OF = "any_of"


class ActionType(Enum):
    SHELL = "shell"
    PROMPT = "prompt"
    HTTP = "http"
    SUBAGENT = "subagent"


@dataclass
class AtomCondition:
    field: str
    matcher: Matcher


@dataclass
class Condition:
    combine: CombineMode = CombineMode.ALL_OF
    atoms: list[AtomCondition] = field(default_factory=list)


@dataclass
class ShellAction:
    command: str
    timeout: float = 30.0


@dataclass
class PromptAction:
    text: str


@dataclass
class HttpAction:
    url: str
    method: str = "POST"
    body: str | None = None
    headers: dict = field(default_factory=dict)


@dataclass
class SubagentAction:
    agent_name: str
    prompt: str


@dataclass
class Action:
    type: ActionType
    shell: ShellAction | None = None
    prompt: PromptAction | None = None
    http: HttpAction | None = None
    subagent: SubagentAction | None = None


@dataclass
class Rule:
    name: str
    event: Event
    action: Action
    condition: Condition | None = None
    asyncio_mode: bool = False  # YAML 的 async 关键字
    only_once: bool = False
    source: str = ""
