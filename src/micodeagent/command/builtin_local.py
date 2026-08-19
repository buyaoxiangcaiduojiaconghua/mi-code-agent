"""5 条纯本地命令"""

from __future__ import annotations

from micodeagent.command.command import Handler
from micodeagent.command.registry import Registry
from micodeagent.command.ui import UI


def make_help_handler(reg: Registry) -> Handler:
    async def _handler(ui: UI) -> None:
        visible = reg.visible()
        width = max((len(c.name) for c in visible), default=0)
        lines = [f"/{c.name.ljust(width)}  {c.description}" for c in visible]
        ui.println("\n".join(lines))

    return _handler


async def handle_status(ui: UI) -> None:
    lines = [
        "MiCodeAgent Status",
        "",
        f"Mode:      {ui.mode().value}",
        f"Tokens:    {ui.usage_in()} in / {ui.usage_out()} out",
        f"Tools:     {ui.tool_count()} enabled",
        f"Memories:  {len(ui.memory_files())} files",
        f"Model:     {ui.model_name()}",
        f"Directory: {ui.cwd()}",
    ]
    ui.println("\n".join(lines))


async def handle_memory(ui: UI) -> None:
    files = ui.memory_files()
    if not files:
        ui.println("无已加载的记忆文件")
        return
    ui.println("\n".join(files))


async def handle_permission(ui: UI) -> None:
    ui.println(ui.mode().value)


async def handle_session(ui: UI) -> None:
    ui.println(f"Session: {ui.session_id()}\nPath: {ui.session_path()}")
