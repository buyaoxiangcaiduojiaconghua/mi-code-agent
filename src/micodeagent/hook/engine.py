"""Hook 引擎：dispatch 主流程"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field

from micodeagent.hook.event import Event, is_blocking
from micodeagent.hook.executor import Executor
from micodeagent.hook.matcher import eval_condition
from micodeagent.hook.rule import Payload, Rule


@dataclass
class DispatchResult:
    """一次 dispatch 的结果。"""

    injected_prompts: list[str] = field(default_factory=list)
    blocked: bool = False
    reason: str = ""
    blocking_hook_name: str = ""


class Engine:
    """Hook 引擎。"""

    def __init__(self, rules: list[Rule], sources: list[str]):
        self._rules = rules
        self._sources = sources
        self._lock = asyncio.Lock()
        self._once_fired: set[str] = set()
        self._executor = Executor()

    @property
    def rules(self) -> list[Rule]:
        return list(self._rules)

    @property
    def sources(self) -> list[str]:
        return list(self._sources)

    async def dispatch(self, event: Event, payload: Payload) -> DispatchResult:
        """遍历 rules，执行匹配的 hook。"""
        result = DispatchResult()
        for rule in self._rules:
            if rule.event != event:
                continue

            async with self._lock:
                if rule.only_once and rule.name in self._once_fired:
                    continue

            if not eval_condition(rule.condition, payload):
                continue

            if rule.asyncio_mode:
                asyncio.create_task(self._executor.run(rule, payload, blocking=False))
                if rule.only_once:
                    async with self._lock:
                        self._once_fired.add(rule.name)
                continue

            outcome = await self._executor.run(rule, payload, blocking=is_blocking(event))

            if outcome.err is not None:
                print(f"[hook {rule.name}] {event.value} failed: {outcome.err}", file=sys.stderr)
                continue

            if outcome.prompt:
                result.injected_prompts.append(outcome.prompt)

            if outcome.blocked and is_blocking(event):
                result.blocked = True
                result.reason = outcome.reason
                result.blocking_hook_name = rule.name
                break

            if rule.only_once:
                async with self._lock:
                    self._once_fired.add(rule.name)

        return result

    async def reset_for_new_session(self) -> None:
        async with self._lock:
            self._once_fired.clear()
