"""Agent ReAct 循环编排

持有 provider、注册中心与权限引擎，执行 ReAct 循环：
每一轮带工具定义发起请求 → 流式收集 → 若有工具调用则保序分批并发执行（经权限判定）并回灌 → 下一轮，
直到模型不再请求工具 / 触达迭代上限 / 用户取消 / 连续未知工具 / 流出错。
以 async generator 吐出 Event 流，供 TUI 消费渲染。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator

from micodeagent import prompt
from micodeagent.compact import ManageInput, TriggerKind, manage_context
from micodeagent.compact.token import estimate_tokens, usage_anchor
from micodeagent.conversation import Conversation
from micodeagent.hook.event import Event as HookEvent
from micodeagent.llm import (
    PromptTooLongError,
    Provider,
    Request,
    System,
    ToolCall,
    ToolResult,
)
from micodeagent.permission import ApprovalRequest, Decision, Mode, Outcome
from micodeagent.permission import Engine as PermissionEngine
from micodeagent.permission.persist import persist_local_allow
from micodeagent.tool import DEFAULT_TIMEOUT, Registry

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════

MAX_ITERATIONS: int = 25
MAX_UNKNOWN_RUN: int = 3
PLAN_REMINDER_INTERVAL: int = 4

NOTICE_MAX_ITER = "（已达最大迭代轮数 25，自动停止；可继续发消息推进。）"
NOTICE_UNKNOWN_TOOLS = "（连续多轮只请求到未注册的工具，自动停止。）"
NOTICE_STREAM_ERR = "（请求出错，本轮已中断。）"
NOTICE_CANCELLED = "（已取消。）"


# ═══════════════════════════════════════════════════════════════════
# 类型
# ═══════════════════════════════════════════════════════════════════


class Phase(Enum):
    START = "start"
    END = "end"


@dataclass
class Usage:
    """一轮请求的 token 用量。"""

    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0


@dataclass
class ToolEvent:
    name: str
    args: str = ""
    phase: Phase = Phase.START
    result: str = ""
    is_error: bool = False


@dataclass
class Event:
    text: str = ""
    tool: ToolEvent | None = None
    usage: Usage | None = None
    iter: int = 0
    notice: str = ""
    approval: ApprovalRequest | None = None
    done: bool = False
    err: Exception | None = None


@dataclass
class _StreamOutcome:
    text: str = ""
    calls: list[ToolCall] = field(default_factory=list)
    usage: object = None
    ok: bool = True
    err: Exception | None = None


@dataclass
class _BatchOutcome:
    results: list[ToolResult] = field(default_factory=list)
    completed: bool = True


# ═══════════════════════════════════════════════════════════════════
# Agent
# ═══════════════════════════════════════════════════════════════════


class Agent:
    """持有 provider、注册中心与权限引擎，执行 ReAct 循环。"""

    def __init__(
        self,
        provider: Provider,
        registry: Registry,
        version: str = "dev",
        engine: PermissionEngine | None = None,
        runtime=None,
        memory_manager=None,
        instruction_text: str = "",
        memory_text: str = "",
        hook_engine=None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._version = version
        self._engine = engine
        self._hook_engine = hook_engine
        if runtime is None:
            from micodeagent.agent.runtime import default_runtime

            runtime = default_runtime()
        self.runtime = runtime
        self._run_lock = asyncio.Lock()
        self._memory_manager = memory_manager
        self._instruction_text = instruction_text
        self._memory_text = memory_text
        self.active_skills: dict[str, str] = {}
        self._skill_catalog: str = ""

    def activate_skill(self, name: str, prompt_body: str) -> None:
        """激活一个 skill，其 SOP 钉到环境上下文。"""
        self.active_skills[name] = prompt_body

    def clear_active_skills(self) -> None:
        """清空已激活的 skill。"""
        self.active_skills.clear()

    def set_skill_catalog(self, catalog: str) -> None:
        """设置 skill 目录（启动时注入）。"""
        self._skill_catalog = catalog

    async def run_to_completion(self, conv: Conversation, task: str = "") -> str:
        """跑到底模式：非交互执行，返回最终文本。"""
        if task:
            conv.add_user(task)
        final_text = ""
        async for ev in self.run(conv, Mode.DEFAULT, asyncio.Event()):
            if ev.text:
                final_text += ev.text
            if ev.err is not None:
                raise ev.err
        return final_text or "（任务完成）"

    def _build_instructions(self) -> str:
        """拼接指令：skill 目录 + 项目指令。"""
        parts = []
        if self._skill_catalog:
            parts.append(self._skill_catalog)
        if self._instruction_text:
            parts.append(self._instruction_text)
        if self.active_skills:
            skill_lines = ["## Active Skills"]
            for name, body in self.active_skills.items():
                skill_lines.append(f"### Skill: {name}\n{body}")
            parts.append("\n\n".join(skill_lines))
        return "\n\n".join(parts)

    async def _dispatch_hook(self, event, payload: dict):
        """触发 hook，把注入的 prompt 写入 reminders。"""
        if self._hook_engine is None:
            return None

        result = await self._hook_engine.dispatch(event, payload)
        if result.injected_prompts:
            self.runtime.append_reminders(result.injected_prompts)
        return result

    async def run(
        self, conv: Conversation, mode: Mode, cancel: asyncio.Event
    ) -> AsyncIterator[Event]:
        """执行 ReAct 循环。"""
        env = prompt.gather_environment(self._version, self._provider.model)
        sys = prompt.build_system_prompt(self._build_instructions(), self._memory_text)
        defs = (
            self._registry.read_only_definitions()
            if mode == Mode.PLAN
            else self._registry.definitions()
        )
        unknown_run = 0

        for it in range(1, MAX_ITERATIONS + 1):
            yield Event(iter=it)
            if cancel.is_set():
                self._finish_cancelled(conv)
                return

            emergency_retried = False

            reminder = ""
            if mode == Mode.PLAN:
                full = it == 1 or (it - 1) % PLAN_REMINDER_INTERVAL == 0
                reminder = prompt.plan_reminder(full)

            # 注入 hook 产生的 reminders
            extra = self.runtime.take_reminders()
            if extra:
                extra_text = "\n\n".join(extra)
                reminder = reminder + "\n\n" + extra_text if reminder else extra_text

            # 触发 PreUserMessage hook
            await self._dispatch_hook(HookEvent.PRE_USER_MESSAGE, {"iter": it})

            # 每轮请求前做上下文管理（自动触发，静默 layer1 + 按需 layer2）
            try:
                await self._manage_context_auto(conv, defs)
            except Exception as e:
                yield Event(err=e)
                return

            req = Request(
                messages=conv.messages(),
                tools=defs,
                system=System(stable=sys, environment=env.render()),
                reminder=reminder,
            )

            so = _StreamOutcome()
            async for ev in self._stream_once(req, cancel, so):
                yield ev

            if not so.ok:
                if cancel.is_set():
                    self._finish_cancelled(conv)
                    return
                # 紧急压缩：PTL 撞墙时重试一次
                if isinstance(so.err, PromptTooLongError) and not emergency_retried:
                    await self._manage_context_emergency(conv, defs)
                    async with self.runtime._lock:
                        self.runtime.usage_anchor = 0
                        self.runtime.anchor_msg_len = 0
                    from micodeagent.compact.const import MANUAL_SAFETY_MARGIN

                    est2 = estimate_tokens(0, conv.messages(), 0)
                    if est2 >= self.runtime.context_window - MANUAL_SAFETY_MARGIN:
                        yield Event(err=so.err)
                        return
                    emergency_retried = True
                    req = Request(
                        messages=conv.messages(),
                        tools=defs,
                        system=System(stable=sys, environment=env.render()),
                        reminder=reminder,
                    )
                    so = _StreamOutcome()
                    async for ev in self._stream_once(req, cancel, so):
                        yield ev
                    if not so.ok:
                        yield Event(err=so.err or Exception(NOTICE_STREAM_ERR))
                        return
                else:
                    yield Event(err=so.err or Exception(NOTICE_STREAM_ERR))
                    return

            if so.usage is not None:
                async with self.runtime._lock:
                    self.runtime.usage_anchor = usage_anchor(so.usage)
                    self.runtime.anchor_msg_len = conv.length()
                yield Event(
                    usage=Usage(
                        input=so.usage.input_tokens,
                        output=so.usage.output_tokens,
                        cache_write=so.usage.cache_write,
                        cache_read=so.usage.cache_read,
                    )
                )

            if not so.calls:
                conv.add_assistant(self._ensure_final(so.text))
                self._maybe_update_memory(conv)
                yield Event(done=True)
                return

            conv.add_assistant_with_tool_calls(so.text, so.calls)
            unknown_run = unknown_run + 1 if self._all_unknown(so.calls) else 0

            outcome = _BatchOutcome()
            async for ev in self._execute_batched(so.calls, mode, cancel, outcome):
                yield ev

            conv.add_tool_results(outcome.results)

            if not outcome.completed:
                self._ensure_assistant_tail(conv, NOTICE_CANCELLED)
                return

            if unknown_run >= MAX_UNKNOWN_RUN:
                yield Event(notice=NOTICE_UNKNOWN_TOOLS)
                self._ensure_assistant_tail(conv, NOTICE_UNKNOWN_TOOLS)
                yield Event(done=True)
                return

        yield Event(notice=NOTICE_MAX_ITER)
        self._ensure_assistant_tail(conv, NOTICE_MAX_ITER)
        yield Event(done=True)

    # ---- 上下文管理 ----

    def _maybe_update_memory(self, conv: Conversation) -> None:
        """每轮自然停下后异步更新记忆。"""
        if self._memory_manager is None:
            return
        msgs = conv.messages()
        if not msgs:
            return
        # 提取最近一轮：从最后一条 user 到末尾
        recent = []
        for m in reversed(msgs):
            recent.insert(0, m)
            if m.role == "user":
                break

        # 触发条件：每 5 轮 或 显式记忆关键词
        self.runtime.turn_count = getattr(self.runtime, "turn_count", 0) + 1
        signal = any(
            kw in (m.content or "")
            for m in recent
            for kw in ("记住", "记忆", "别忘", "remember", "memo")
        )
        if self.runtime.turn_count % 5 == 0 or signal:
            asyncio.create_task(self._memory_manager.update_async(recent))

    async def _manage_context_auto(self, conv: Conversation, defs: list) -> None:
        """每轮请求前做自动上下文管理。"""
        await self._run_manage(conv, defs, TriggerKind.AUTO)

    async def _manage_context_emergency(self, conv: Conversation, defs: list) -> None:
        """紧急压缩（PTL 撞墙时）。"""
        await self._run_manage(conv, defs, TriggerKind.EMERGENCY)

    async def _run_manage(self, conv: Conversation, defs: list, trigger: TriggerKind) -> None:
        async with self.runtime._lock:
            anchor = self.runtime.usage_anchor
            anchor_len = self.runtime.anchor_msg_len
            cw = self.runtime.context_window
        est = estimate_tokens(anchor, conv.messages(), anchor_len)
        in_ = ManageInput(
            conv=conv,
            provider=self._provider,
            context_window=cw,
            tool_defs=defs,
            replacement=self.runtime.replacement,
            recovery=self.runtime.recovery,
            auto_tracking=self.runtime.auto_tracking,
            session=self.runtime.session,
            usage_anchor=anchor,
            anchor_msg_len=anchor_len,
            estimated_token=est,
            trigger=trigger,
        )
        await manage_context(in_)

    async def run_force_compact(self, conv: Conversation, tool_defs: list) -> tuple[int, int]:
        """手动触发压缩，供 TUI 调用。"""
        async with self._run_lock:
            async with self.runtime._lock:
                anchor = self.runtime.usage_anchor
                anchor_len = self.runtime.anchor_msg_len
                cw = self.runtime.context_window
            est = estimate_tokens(anchor, conv.messages(), anchor_len)
            in_ = ManageInput(
                conv=conv,
                provider=self._provider,
                context_window=cw,
                tool_defs=tool_defs,
                replacement=self.runtime.replacement,
                recovery=self.runtime.recovery,
                auto_tracking=self.runtime.auto_tracking,
                session=self.runtime.session,
                usage_anchor=anchor,
                anchor_msg_len=anchor_len,
                estimated_token=est,
                trigger=TriggerKind.MANUAL,
            )
            out = await manage_context(in_)
            return (out.before_tokens, out.after_tokens)

    # ---- 单轮流式收集 ----

    async def _stream_once(
        self,
        req: Request,
        cancel: asyncio.Event,
        outcome: _StreamOutcome,
    ) -> AsyncIterator[Event]:
        async for ev in self._provider.stream(req):
            if cancel.is_set():
                outcome.ok = False
                return
            if ev.err is not None:
                outcome.err = ev.err
                outcome.ok = False
                return
            if ev.usage is not None:
                outcome.usage = ev.usage
            if ev.tool_calls:
                outcome.calls.extend(ev.tool_calls)
            if ev.text:
                outcome.text += ev.text
                yield Event(text=ev.text)

        if cancel.is_set():
            outcome.ok = False

    # ---- 保序分批并发执行（含权限判定）----

    async def _execute_batched(
        self,
        calls: list[ToolCall],
        mode: Mode,
        cancel: asyncio.Event,
        outcome: _BatchOutcome,
    ) -> AsyncIterator[Event]:
        n = len(calls)
        results: list[ToolResult | None] = [None] * n
        i = 0
        completed = True

        while i < n:
            if cancel.is_set():
                for k in range(i, n):
                    if results[k] is None:
                        results[k] = ToolResult(
                            tool_call_id=calls[k].id, content=NOTICE_CANCELLED, is_error=True
                        )
                completed = False
                break

            if self._registry.is_read_only(calls[i].name):
                # 连续只读区间 [i, j)
                j = i
                while j < n and self._registry.is_read_only(calls[j].name):
                    j += 1

                # 先逐个权限检查
                decisions: list[Decision] = []
                reasons: list[str] = []
                for k in range(i, j):
                    d, reason = self._check(mode, calls[k], True)
                    decisions.append(d)
                    reasons.append(reason)

                # 按序发 START
                for k in range(i, j):
                    yield Event(
                        tool=ToolEvent(
                            name=calls[k].name,
                            args=self._args_preview(calls[k].input),
                            phase=Phase.START,
                        )
                    )

                # 预置 DENY 结果，收集 ALLOW 的并发执行
                allow_indices = []
                for k in range(i, j):
                    if decisions[k - i] == Decision.DENY:
                        results[k] = ToolResult(
                            tool_call_id=calls[k].id, content=reasons[k - i], is_error=True
                        )
                    else:
                        allow_indices.append(k)

                async def run_one(k: int) -> None:
                    if cancel.is_set():
                        results[k] = ToolResult(
                            tool_call_id=calls[k].id, content=NOTICE_CANCELLED, is_error=True
                        )
                        return
                    r = await self._registry.execute(
                        calls[k].name, calls[k].input, timeout=DEFAULT_TIMEOUT
                    )
                    results[k] = ToolResult(
                        tool_call_id=calls[k].id, content=r.content, is_error=r.is_error
                    )

                if allow_indices:
                    await asyncio.gather(*[run_one(k) for k in allow_indices])

                # 按序发 END
                for k in range(i, j):
                    yield Event(
                        tool=ToolEvent(
                            name=calls[k].name,
                            phase=Phase.END,
                            result=results[k].content,
                            is_error=results[k].is_error,
                        )
                    )
                i = j
            else:
                # 串行执行单个有副作用工具（含权限判定 + 人在回路 + hook 拦截）
                yield Event(
                    tool=ToolEvent(
                        name=calls[i].name,
                        args=self._args_preview(calls[i].input),
                        phase=Phase.START,
                    )
                )
                # PreToolUse hook 拦截
                hook_result = await self._dispatch_hook(
                    HookEvent.PRE_TOOL_USE,
                    {"tool_name": calls[i].name, "tool_input": calls[i].input},
                )
                if hook_result is not None and hook_result.blocked:
                    results[i] = ToolResult(
                        tool_call_id=calls[i].id,
                        content=f"[hook {hook_result.blocking_hook_name}] {hook_result.reason}",
                        is_error=True,
                    )
                    yield Event(
                        tool=ToolEvent(
                            name=calls[i].name,
                            phase=Phase.END,
                            result=results[i].content,
                            is_error=True,
                        )
                    )
                    i += 1
                    continue

                decision, reason = self._check(mode, calls[i], False)
                if cancel.is_set():
                    results[i] = ToolResult(
                        tool_call_id=calls[i].id, content=NOTICE_CANCELLED, is_error=True
                    )
                    completed = False
                elif decision == Decision.DENY:
                    results[i] = ToolResult(tool_call_id=calls[i].id, content=reason, is_error=True)
                elif decision == Decision.ASK:
                    # 人在回路
                    respond = asyncio.get_running_loop().create_future()
                    yield Event(
                        approval=ApprovalRequest(
                            name=calls[i].name,
                            args=self._args_preview(calls[i].input),
                            reason=reason,
                            respond=respond,
                        )
                    )
                    try:
                        user_outcome = await respond
                    except asyncio.CancelledError:
                        raise
                    if user_outcome == Outcome.DENY_ONCE:
                        results[i] = ToolResult(
                            tool_call_id=calls[i].id,
                            content=f"用户拒绝了工具调用: {reason}",
                            is_error=True,
                        )
                    else:
                        if user_outcome == Outcome.ALLOW_FOREVER:
                            try:
                                persist_local_allow(self._engine, calls[i])
                            except Exception as e:
                                logger.warning("持久化 allow 规则失败: %s", e)
                        r = await self._registry.execute(
                            calls[i].name, calls[i].input, timeout=DEFAULT_TIMEOUT
                        )
                        results[i] = ToolResult(
                            tool_call_id=calls[i].id, content=r.content, is_error=r.is_error
                        )
                else:  # ALLOW
                    r = await self._registry.execute(
                        calls[i].name, calls[i].input, timeout=DEFAULT_TIMEOUT
                    )
                    results[i] = ToolResult(
                        tool_call_id=calls[i].id, content=r.content, is_error=r.is_error
                    )
                yield Event(
                    tool=ToolEvent(
                        name=calls[i].name,
                        phase=Phase.END,
                        result=results[i].content,
                        is_error=results[i].is_error,
                    )
                )
                i += 1

        outcome.results = [r for r in results if r is not None]
        outcome.completed = completed

    def _check(self, mode: Mode, call: ToolCall, read_only: bool) -> tuple[Decision, str]:
        """权限检查；无引擎则全部放行。"""
        if self._engine is None:
            return (Decision.ALLOW, "")
        return self._engine.check(mode, call, read_only)

    # ---- 辅助函数 ----

    @staticmethod
    def _args_preview(input_str: str) -> str:
        if len(input_str) > 80:
            return input_str[:77] + "..."
        return input_str

    def _all_unknown(self, calls: list[ToolCall]) -> bool:
        if not calls:
            return False
        for c in calls:
            if self._registry.get(c.name) is not None:
                return False
        return True

    @staticmethod
    def _ensure_final(text: str) -> str:
        if text.strip():
            return text
        return "（任务完成）"

    def _ensure_assistant_tail(self, conv: Conversation, fallback: str) -> None:
        if conv.last_role() != "assistant":
            conv.add_assistant(fallback)

    def _finish_cancelled(self, conv: Conversation) -> None:
        self._ensure_assistant_tail(conv, NOTICE_CANCELLED)
