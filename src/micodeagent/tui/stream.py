"""TUI 流式事件处理模块

处理提交（/plan /do 命令识别 + 启动 Agent Loop），
消费 Agent.run() 的 Event 流，处理文本增量、工具行、用量、进度、通知与错误。
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from rich.markdown import Markdown
from rich.text import Text
from textual.widgets import RichLog, Static

from micodeagent import __version__
from micodeagent.agent import Agent, Phase
from micodeagent.permission import Outcome
from micodeagent.tui.view import (
    error_block,
    streaming_view,
    tool_line,
    tool_result_summary,
    user_block,
)

if TYPE_CHECKING:
    from micodeagent.tui.app import MiCodeAgentApp


async def submit(app: "MiCodeAgentApp", text: str) -> None:
    """处理用户提交：slash 命令走分发，普通文本启动一轮 Agent Loop。"""
    if await app.dispatch_slash(text):
        return

    # 普通文本
    _start_turn(app, text)


def _make_agent(app: "MiCodeAgentApp") -> Agent:
    """构造 Agent 并完成 skill 接线。"""
    agent = Agent(
        app.provider,
        app._tool_registry,
        __version__,
        app._engine,
        app.runtime,
        app.mem_mgr,
        app.instruction_text,
        app.memory_text,
        hook_engine=app.hook_engine,
    )
    # skill 接线
    agent.set_skill_catalog(app._build_skill_catalog())
    if app.load_skill_tool is not None:
        app.load_skill_tool.set_loader(app.skill_loader)
        app.load_skill_tool.set_agent(agent)
    return agent


def _handle_compact(app: "MiCodeAgentApp") -> None:
    """手动触发上下文压缩。"""
    agent = _make_agent(app)

    async def _run():
        try:
            defs = app._tool_registry.definitions()
            before, after = await agent.run_force_compact(app.conv, defs)
            app.query_one("#log", RichLog).write(
                Text(f"已压缩，token 从 {before} 降至 {after}", style="bold #7ee787")
            )
        except Exception as e:
            app.query_one("#log", RichLog).write(Text(f"压缩失败: {e}", style="bold #f85149"))

    asyncio.create_task(_run())


def _handle_resume(app: "MiCodeAgentApp") -> None:
    """恢复历史会话（自动恢复最近一个）。"""
    from pathlib import Path

    from micodeagent.compact.state import open_session_context
    from micodeagent.session import list_sessions, load_session

    sessions = list_sessions(app.sessions_dir)
    if not sessions:
        app.query_one("#log", RichLog).write(Text("无可用历史会话", style="dim"))
        return

    info = sessions[0]  # 最新会话
    msgs = load_session(info.dir)

    # 重建会话
    from micodeagent.conversation import Conversation

    app.conv = Conversation.from_messages(
        msgs,
        on_append=app.writer.on_append if app.writer else None,
        on_replace=app.writer.on_replace if app.writer else None,
    )
    # 更新 runtime 的 session 上下文
    app.runtime.session = open_session_context(str(Path.cwd().resolve()), info.id)

    app.query_one("#log", RichLog).write(
        Text(f"已恢复会话 {info.id}，共 {len(msgs)} 条消息", style="bold #7ee787")
    )


def _start_turn(app: "MiCodeAgentApp", user_text: str) -> None:
    """启动一轮 Agent Loop。"""
    app.conv.add_user(user_text)
    app.query_one("#log", RichLog).write(user_block(user_text))

    app.cur_reply = ""
    app.cur_tools = []
    app.iter = 0
    app.turn_start = time.monotonic()
    app.turn_cancel = asyncio.Event()
    app.state = app.SessionState.STREAMING

    app._stream_task = asyncio.create_task(consume_agent_events(app))
    app._timer = app.set_interval(0.1, app._tick)


async def consume_agent_events(app: "MiCodeAgentApp") -> None:
    """消费 Agent.run() 的 Event 流，分派渲染。"""
    agent = _make_agent(app)

    try:
        async for ev in agent.run(app.conv, app.mode, app.turn_cancel):
            if ev.err is not None:
                _finish_with_error(app, ev.err)
                return

            if ev.approval is not None:
                # 人在回路：暂停，等待用户决策（generator 阻塞在 await respond）
                app.pending = ev.approval
                app.approve_cursor = 0
                app.state = app.SessionState.APPROVING
                app._render_approval()
                continue

            if ev.text:
                app.cur_reply += ev.text
                _refresh_streaming(app)

            if ev.tool and ev.tool.phase == Phase.START:
                # 先提交 preamble 到对话区
                if app.cur_reply.strip():
                    app.query_one("#log", RichLog).write(Markdown(app.cur_reply))
                    app.cur_reply = ""
                app.cur_tools.append({"name": ev.tool.name, "args": ev.tool.args})
                _refresh_streaming(app)

            if ev.tool and ev.tool.phase == Phase.END:
                log = app.query_one("#log", RichLog)
                # FIFO 弹出队首（PHASE_START/END 均按调用序发出）
                if app.cur_tools:
                    cur = app.cur_tools.pop(0)
                    args = cur["args"]
                else:
                    args = ""
                log.write(tool_line(ev.tool.name, args))
                log.write(tool_result_summary(ev.tool.result, ev.tool.is_error))
                _refresh_streaming(app)

            if ev.usage is not None:
                app.usage_in += ev.usage.input
                app.usage_out += ev.usage.output
                app._update_status_bar()

            if ev.iter:
                app.iter = ev.iter
                _refresh_streaming(app)

            if ev.notice:
                app.query_one("#log", RichLog).write(Text(ev.notice, style="dim"))

            if ev.done:
                if app.cur_reply.strip():
                    app.query_one("#log", RichLog).write(Markdown(app.cur_reply))
                finish_turn(app)
                return

    except asyncio.CancelledError:
        raise
    except Exception as e:
        _finish_with_error(app, e)


def tick(app: "MiCodeAgentApp") -> None:
    """计时回调：流式期间刷新进行中指示。"""
    if app.state != app.SessionState.STREAMING:
        return
    _refresh_streaming(app)


def _refresh_streaming(app: "MiCodeAgentApp") -> None:
    """刷新动态区显示。"""
    elapsed = int(time.monotonic() - app.turn_start)
    if app.cur_tools:
        # 多个并发工具执行中指示
        lines = [f"● {t['name']}({t['args']})  Running…" for t in app.cur_tools]
        app.query_one("#streaming", Static).update("\n".join(lines))
    elif app.cur_reply:
        app.query_one("#streaming", Static).update(streaming_view(app.cur_reply, elapsed, app.iter))
    else:
        suffix = f" · 第 {app.iter} 轮" if app.iter > 0 else ""
        app.query_one("#streaming", Static).update(f"Imagining… ({elapsed}s{suffix})")


def _finish_with_error(app: "MiCodeAgentApp", err: Exception) -> None:
    """出错：以可区分样式追加错误，回到空闲（不退出）。"""
    app.query_one("#log", RichLog).write(error_block(err))
    finish_turn(app)


def finish_turn(app: "MiCodeAgentApp") -> None:
    """收尾：停计时、清缓冲、切回空闲态（mode 与 usage 跨轮保持）。"""
    if app._timer is not None:
        app._timer.stop()
        app._timer = None
    app._stream_task = None
    app.cur_reply = ""
    app.cur_tools = []
    app.iter = 0
    app.turn_cancel = None
    app.query_one("#streaming", Static).update("")
    app.state = app.SessionState.IDLE


def update_approving(app: "MiCodeAgentApp", key: str) -> bool:
    """审批状态下处理键盘输入，返回是否已处理。"""
    if app.pending is None:
        return False

    if key in ("up", "k"):
        app.approve_cursor = max(0, app.approve_cursor - 1)
        app._render_approval()
        return True

    if key in ("down", "j"):
        app.approve_cursor = min(2, app.approve_cursor + 1)
        app._render_approval()
        return True

    if key in ("enter", "space"):
        _submit_approval(app, app.approve_cursor)
        return True

    if key in ("1", "2", "3"):
        _submit_approval(app, int(key) - 1)
        return True

    if key == "y":
        _submit_approval(app, 0)
        return True

    if key in ("n", "d"):
        _submit_approval(app, 2)
        return True

    return False


def _submit_approval(app: "MiCodeAgentApp", idx: int) -> None:
    outcome = [Outcome.ALLOW_ONCE, Outcome.ALLOW_FOREVER, Outcome.DENY_ONCE][idx]
    if app.pending is not None:
        app.pending.respond.set_result(outcome)
    app._clear_approval()
    app.state = app.SessionState.STREAMING
