"""MiCodeAgent TUI 主应用

基于 Textual 的终端界面，承载状态机（选择 / 空闲 / 流式 / 待批准）、
输入提交、流式消费、计时、权限模式与 provider 选择。
"""

from __future__ import annotations

import asyncio
import os
from enum import Enum

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import OptionList, RichLog, Static, TextArea

from micodeagent import __version__
from micodeagent.command import Kind, parse
from micodeagent.command.builtins import register_builtins
from micodeagent.command.registry import Registry as CommandRegistry
from micodeagent.config import ProviderConfig
from micodeagent.conversation import Conversation
from micodeagent.llm import Provider, new_provider
from micodeagent.permission import ApprovalRequest, Mode, Outcome, next_mode
from micodeagent.permission import Engine as PermissionEngine
from micodeagent.prompt import render_banner
from micodeagent.tool import Registry
from micodeagent.tui import stream as stream_mod
from micodeagent.tui.complete import CompletionMenu
from micodeagent.tui.select import build_option_list
from micodeagent.tui.view import status_bar


class SessionState(Enum):
    """TUI 会话状态"""

    SELECTING = "selecting"  # 多 provider 时的选择界面
    IDLE = "idle"  # 等待用户输入
    STREAMING = "streaming"  # 等待/接收模型流
    APPROVING = "approving"  # 等待用户审批工具调用


class SubmitTextArea(TextArea):
    """多行输入框：Enter 提交，Alt+Enter 换行，Shift+Tab 切换模式。"""

    class Submitted(Message):
        """用户按 Enter 提交输入。"""

    class CycleMode(Message):
        """用户按 Shift+Tab 切换权限模式。"""

    def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.prevent_default()
            self.post_message(self.Submitted())
        elif event.key == "alt+enter":
            self.insert("\n")
            event.prevent_default()
        elif event.key == "shift+tab":
            event.prevent_default()
            self.post_message(self.CycleMode())
        else:
            super()._on_key(event)


class _UIAdapter:
    """把 MiCodeAgentApp 适配成命令系统的 UI Protocol。"""

    def __init__(self, app: "MiCodeAgentApp"):
        self._app = app

    def println(self, msg: str) -> None:
        self._app._ui_println(msg)

    def error(self, msg: str) -> None:
        self._app._ui_error(msg)

    def mode(self) -> Mode:
        return self._app.mode

    def usage_in(self) -> int:
        return self._app.usage_in

    def usage_out(self) -> int:
        return self._app.usage_out

    def model_name(self) -> str:
        return self._app.provider.model if self._app.provider else ""

    def cwd(self) -> str:
        return self._app._cwd

    def tool_count(self) -> int:
        return self._app._tool_registry.count()

    def memory_files(self) -> list[str]:
        if self._app.mem_mgr is None:
            return []
        project, user = self._app.mem_mgr.list_files()
        return project + user

    def session_path(self) -> str:
        return self._app.writer.path if self._app.writer else ""

    def session_id(self) -> str:
        if self._app.runtime and self._app.runtime.session:
            return self._app.runtime.session.session_id
        return ""

    def idle(self) -> bool:
        return self._app.state == self._app.SessionState.IDLE

    def set_mode(self, m: Mode) -> None:
        self._app.mode = m
        self._app._update_status_bar()

    def inject_and_send(self, label: str, preset: str) -> None:
        self._app._ui_inject_and_send(label, preset)

    def quit(self) -> None:
        self._app.action_quit()

    def force_compact(self) -> None:
        self._app._ui_force_compact()

    def open_resume_menu(self) -> None:
        self._app._ui_open_resume_menu()

    def clear_and_new_session(self) -> None:
        self._app._ui_clear_and_new_session()


class MiCodeAgentApp(App):
    """MiCodeAgent 主应用"""

    SessionState = SessionState

    CSS = """
    #log {
        height: 1fr;
        padding: 0 1;
    }
    #streaming {
        height: auto;
        padding: 0 1;
        color: #c9d1d9;
    }
    #input-area {
        height: auto;
        border-top: solid #30363d;
        padding: 0 1;
    }
    #prompt {
        width: 1;
        color: #58a6ff;
        text-style: bold;
    }
    #input {
        width: 1fr;
        height: 3;
        border: none;
        padding: 0;
    }
    #statusbar {
        height: 1;
        background: #161b22;
        color: #8b949e;
        padding: 0 1;
    }
    #selector {
        height: 1fr;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "cancel_or_quit", "取消/退出"),
        Binding("escape", "cancel_turn", "取消本轮"),
        Binding("shift+tab", "cycle_mode", "切换模式"),
    ]

    def __init__(
        self,
        providers: list[ProviderConfig],
        registry: Registry,
        engine: PermissionEngine,
        runtime=None,
        writer=None,
        mem_mgr=None,
        instruction_text: str = "",
        memory_text: str = "",
        sessions_dir: str = "",
        skill_loader=None,
        load_skill_tool=None,
        hook_engine=None,
    ):
        super().__init__()
        self.providers = providers
        self.provider: Provider | None = None
        self._tool_registry = registry
        self._engine = engine
        self.runtime = runtime
        self.writer = writer
        self.mem_mgr = mem_mgr
        self.instruction_text = instruction_text
        self.memory_text = memory_text
        self.sessions_dir = sessions_dir
        self.skill_loader = skill_loader
        self.load_skill_tool = load_skill_tool
        self.hook_engine = hook_engine
        if runtime is not None and hook_engine is not None:
            runtime.hook_engine = hook_engine
        self.conv = Conversation(
            on_append=writer.on_append if writer else None,
            on_replace=writer.on_replace if writer else None,
        )

        # 会话状态
        self.state: SessionState = SessionState.IDLE

        # 权限模式（跨轮保持）
        self.mode: Mode = engine.start_mode

        # 当前迭代轮次
        self.iter: int = 0

        # 会话累计 token 用量
        self.usage_in: int = 0
        self.usage_out: int = 0

        # 本轮回复缓冲与计时起点
        self.cur_reply: str = ""
        self.turn_start: float = 0.0

        # 流式消费 task 与计时器
        self._stream_task: asyncio.Task | None = None
        self._timer = None

        # 工具执行中指示（并发批可能有多个）
        self.cur_tools: list[dict] = []

        # 本轮取消事件
        self.turn_cancel: asyncio.Event | None = None

        # 待批准请求与光标
        self.pending: ApprovalRequest | None = None
        self.approve_cursor: int = 0

        # 命令注册中心与补全菜单
        self._cwd = os.getcwd()
        self.cmd_registry = CommandRegistry()
        register_builtins(self.cmd_registry)
        self._register_skill_command()
        self.completion = CompletionMenu()
        self._pending_println: list[str] = []

    def _register_skill_command(self) -> None:
        """注册 /skill 命令（列出可用 skill）。"""
        from micodeagent.command.command import Command, Kind

        async def _handle(ui):
            if self.skill_loader is None:
                ui.println("Skill 系统未初始化")
                return
            catalog = self.skill_loader.get_catalog()
            if not catalog:
                ui.println("无可用 Skill")
                return
            lines = []
            for name, desc in catalog:
                source = self.skill_loader.get_source_label(name)
                lines.append(f"  {name:<20} {desc}  [{source}]")
            ui.println("\n".join(lines))

        self.cmd_registry.register(
            Command(name="skill", description="列出可用 Skill", kind=Kind.LOCAL, handler=_handle)
        )

    def _build_skill_catalog(self) -> str:
        """构造 skill 目录文本。"""
        if self.skill_loader is None:
            return ""
        catalog = self.skill_loader.get_catalog()
        if not catalog:
            return ""
        lines = ["You can use the following Skills:", ""]
        for name, desc in catalog:
            lines.append(f"- {name}: {desc}")
        lines.append("")
        lines.append("If the user's request matches a Skill, call load_skill to activate it.")
        return "\n".join(lines)

    # ---- 布局 ----

    def compose(self) -> ComposeResult:
        yield RichLog(id="log", wrap=True, markup=False, highlight=True)
        yield Static("", id="streaming")
        with Horizontal(id="input-area"):
            yield Static("❯", id="prompt")
            yield SubmitTextArea("", id="input", soft_wrap=True)
        yield Static("", id="completion")
        yield Static("", id="statusbar")

    def on_mount(self) -> None:
        self.query_one("#log", RichLog).write(
            Text(render_banner(__version__, os.getcwd()), style="dim")
        )

        # 自动选第一个 provider，直接进入对话
        self.provider = new_provider(self.providers[0])
        self.state = SessionState.IDLE
        self._update_status_bar()

    # ---- provider 选择 ----

    def _enter_selecting(self) -> None:
        self.mount(build_option_list(self.providers))
        self.query_one("#log").display = False
        self.query_one("#streaming").display = False
        self.query_one("#input-area").display = False
        self.query_one("#statusbar").display = False
        self.state = SessionState.SELECTING

    def _exit_selecting(self) -> None:
        self.query_one("#selector", OptionList).remove()
        self.query_one("#log").display = True
        self.query_one("#streaming").display = True
        self.query_one("#input-area").display = True
        self.query_one("#statusbar").display = True

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        cfg = self.providers[event.option_index]
        self.provider = new_provider(cfg)
        self._exit_selecting()
        self._update_status_bar()
        self.state = SessionState.IDLE
        self.query_one("#input").focus()

    # ---- 状态栏 ----

    def _update_status_bar(self) -> None:
        if self.provider is not None:
            width = self.size.width or 80
            self.query_one("#statusbar", Static).update(
                status_bar(self.mode, self.provider.model, self.usage_in, self.usage_out, width)
            )

    # ---- 输入提交 ----

    async def on_submit_text_area_submitted(self) -> None:
        await self._submit()

    def on_submit_text_area_cycle_mode(self) -> None:
        self.action_cycle_mode()

    async def _submit(self) -> None:
        if self.state != SessionState.IDLE:
            return

        input_widget = self.query_one("#input", TextArea)
        text = input_widget.text.strip()
        input_widget.clear()

        if not text:
            return

        await stream_mod.submit(self, text)

    def _tick(self) -> None:
        stream_mod.tick(self)

    # ---- 命令系统 UI Protocol 实现 ----

    # 只读查询
    def _ui_mode(self) -> Mode:
        return self.mode

    def _ui_usage_in(self) -> int:
        return self.usage_in

    def _ui_usage_out(self) -> int:
        return self.usage_out

    def _ui_model_name(self) -> str:
        return self.provider.model if self.provider else ""

    def _ui_cwd(self) -> str:
        return self._cwd

    def _ui_tool_count(self) -> int:
        return self._tool_registry.count()

    def _ui_memory_files(self) -> list[str]:
        if self.mem_mgr is None:
            return []
        project, user = self.mem_mgr.list_files()
        return project + user

    def _ui_session_path(self) -> str:
        return self.writer.path if self.writer else ""

    def _ui_session_id(self) -> str:
        if self.runtime and self.runtime.session:
            return self.runtime.session.session_id
        return ""

    def _ui_idle(self) -> bool:
        return self.state == SessionState.IDLE

    # 写入
    def _ui_println(self, msg: str) -> None:
        self._pending_println.append(msg)

    def _ui_error(self, msg: str) -> None:
        self._pending_println.append(f"ERROR\x00{msg}")

    def _ui_set_mode(self, m: Mode) -> None:
        self.mode = m
        self._update_status_bar()

    def _ui_quit(self) -> None:
        self.action_quit()

    def _ui_force_compact(self) -> None:
        from micodeagent.tui.stream import _handle_compact

        _handle_compact(self)

    def _ui_open_resume_menu(self) -> None:
        from micodeagent.tui.stream import _handle_resume

        _handle_resume(self)

    def _ui_clear_and_new_session(self) -> None:
        from micodeagent.compact.state import new_session_context
        from micodeagent.session.writer import Writer

        if self.writer:
            try:
                self.writer.close()
            except Exception:
                pass
        try:
            new_ctx = new_session_context(self._cwd)
            new_writer = Writer(new_ctx.session_dir)
        except Exception as e:
            self._ui_error(str(e))
            self._flush_println()
            return
        self.writer = new_writer
        self.conv = Conversation(
            on_append=new_writer.on_append,
            on_replace=new_writer.on_replace,
        )
        self.runtime.reset_for_new_session(new_ctx)
        self.iter = 0
        self.usage_in = 0
        self.usage_out = 0
        self.query_one("#log", RichLog).clear()

    def _ui_inject_and_send(self, label: str, preset: str) -> None:
        self.conv.add_user(preset)
        stream_mod._start_turn(self, label)

    def _flush_println(self) -> None:
        log = self.query_one("#log", RichLog)
        for msg in self._pending_println:
            if msg.startswith("ERROR\x00"):
                log.write(Text(msg[6:], style="bold #f85149"))
            else:
                log.write(Text(msg, style="dim"))
        self._pending_println = []

    async def dispatch_slash(self, text: str) -> bool:
        """分发 slash 命令。"""
        name, is_slash = parse(text)
        if not is_slash:
            return False

        cmd = self.cmd_registry.lookup(name)
        if cmd is None:
            self._ui_println("未知命令，输入 /help 查看可用命令")
            self._flush_println()
            return True

        if cmd.kind in (Kind.UI, Kind.PROMPT) and not self._ui_idle():
            self._ui_error("请等待当前任务完成")
            self._flush_println()
            return True

        try:
            await cmd.handler(_UIAdapter(self))
        except Exception as exc:
            self._ui_error(str(exc))

        self._flush_println()
        return True

    # ---- 补全菜单 ----

    def _sync_completion_from_input(self) -> None:
        input_widget = self.query_one("#input", TextArea)
        self.completion.update(input_widget.text, self.cmd_registry)
        self._render_completion()

    def _render_completion(self) -> None:
        text = self.completion.render(self.size.width) if self.completion.active else ""
        self.query_one("#completion", Static).update(text)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "input":
            self._sync_completion_from_input()

    async def _handle_completion_key(self, event: events.Key) -> bool:
        if not self.completion.active:
            return False
        if event.key == "up":
            self.completion.move_up()
            self._render_completion()
            event.stop()
            return True
        if event.key == "down":
            self.completion.move_down()
            self._render_completion()
            event.stop()
            return True
        if event.key == "escape":
            self.completion.hide()
            self._render_completion()
            event.stop()
            return True
        if event.key in ("enter", "tab"):
            sel = self.completion.selected()
            if sel is not None:
                input_widget = self.query_one("#input", TextArea)
                input_widget.text = "/" + sel.name
                self.completion.hide()
                self._render_completion()
                await self._submit()
                event.stop()
            else:
                self.completion.hide()
                self._render_completion()
                event.stop()
            return True
        return False

    # ---- 待批准渲染 ----

    def _render_approval(self) -> None:
        if self.pending is not None:
            from micodeagent.tui.view import approval_block

            self.query_one("#log", RichLog).write(
                Text.from_markup(approval_block(self.pending, self.approve_cursor))
            )

    def _clear_approval(self) -> None:
        self.pending = None
        self.approve_cursor = 0

    # ---- 按键 ----

    async def on_key(self, event: events.Key) -> None:
        """审批态优先处理方向键/确认键/数字键；空闲态处理补全键位。"""
        if self.state == SessionState.APPROVING:
            if stream_mod.update_approving(self, event.key):
                event.prevent_default()
                event.stop()
            return

        if self.state == SessionState.IDLE:
            if await self._handle_completion_key(event):
                return

    def action_cycle_mode(self) -> None:
        """Shift+Tab：仅在空闲态循环切换权限模式。"""
        if self.state != SessionState.IDLE:
            return
        self.mode = next_mode(self.mode)
        self._update_status_bar()
        self.query_one("#log", RichLog).write(
            Text(f"🔧 已切换到 {self.mode} 模式", style="bold #d2a8ff")
        )

    def action_cancel_or_quit(self) -> None:
        """Ctrl+C：流式/审批态取消本轮，空闲态退出。"""
        if self.state in (SessionState.STREAMING, SessionState.APPROVING):
            self._cancel_turn()
        else:
            self.action_quit()

    def action_cancel_turn(self) -> None:
        """Esc：流式/审批态取消本轮。"""
        if self.state in (SessionState.STREAMING, SessionState.APPROVING):
            self._cancel_turn()

    def _cancel_turn(self) -> None:
        # 审批态：先兜底解开 agent 等待，再取消
        if self.state == SessionState.APPROVING and self.pending is not None:
            try:
                self.pending.respond.set_result(Outcome.DENY_ONCE)
            except Exception:
                pass
            self._clear_approval()
        if self.turn_cancel is not None:
            self.turn_cancel.set()

    # ---- 退出 ----

    def action_quit(self) -> None:
        if self._stream_task is not None and not self._stream_task.done():
            self._stream_task.cancel()
        self.exit()


def new_app(
    providers: list[ProviderConfig],
    registry: Registry,
    engine: PermissionEngine,
) -> MiCodeAgentApp:
    """创建 MiCodeAgentApp 实例的工厂函数"""
    return MiCodeAgentApp(providers, registry, engine)
