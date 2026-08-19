"""注册 12 条内置命令"""

from __future__ import annotations

from micodeagent.command import builtin_local, builtin_prompt, builtin_ui
from micodeagent.command.command import Command, Kind
from micodeagent.command.registry import Registry


def register_builtins(reg: Registry) -> None:
    """按字典序注册 12 条内置命令。"""
    help_cmd = Command(
        name="help",
        description="列出所有可用命令",
        kind=Kind.LOCAL,
        handler=builtin_local.make_help_handler(reg),
    )
    commands = [
        help_cmd,
        Command(
            name="clear",
            description="清空当前会话并开启新 session",
            kind=Kind.UI,
            handler=builtin_ui.handle_clear,
        ),
        Command(
            name="compact",
            description="手动压缩上下文",
            kind=Kind.UI,
            handler=builtin_ui.handle_compact,
        ),
        Command(
            name="do",
            description="退出计划模式并按计划执行",
            kind=Kind.PROMPT,
            handler=builtin_prompt.handle_do,
        ),
        Command(
            name="exit",
            description="退出 MiCodeAgent",
            kind=Kind.UI,
            handler=builtin_ui.handle_exit,
        ),
        Command(
            name="memory",
            description="列出已加载的记忆文件",
            kind=Kind.LOCAL,
            handler=builtin_local.handle_memory,
        ),
        Command(
            name="permission",
            description="显示当前权限模式",
            kind=Kind.LOCAL,
            handler=builtin_local.handle_permission,
        ),
        Command(
            name="plan",
            description="进入计划模式（只读工具）",
            kind=Kind.UI,
            handler=builtin_ui.handle_plan,
        ),
        Command(
            name="resume",
            description="恢复历史会话",
            kind=Kind.UI,
            handler=builtin_ui.handle_resume,
        ),
        Command(
            name="review",
            description="审查代码变更并给出建议",
            kind=Kind.PROMPT,
            handler=builtin_prompt.handle_review,
        ),
        Command(
            name="session",
            description="显示当前会话信息",
            kind=Kind.LOCAL,
            handler=builtin_local.handle_session,
        ),
        Command(
            name="status",
            description="显示运行状态",
            kind=Kind.LOCAL,
            handler=builtin_local.handle_status,
        ),
    ]
    for cmd in commands:
        reg.register(cmd)
