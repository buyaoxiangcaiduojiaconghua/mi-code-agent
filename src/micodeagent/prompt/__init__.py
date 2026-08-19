"""提示词与启动横幅模块

提供系统提示装配、ASCII 猫 banner 与 banner 渲染函数，
以及环境信息、补充消息注入等子模块。
"""

from micodeagent.prompt.environment import Environment, gather_environment
from micodeagent.prompt.modules import Module, fixed_modules, optional_modules
from micodeagent.prompt.reminder import EXECUTE_DIRECTIVE, plan_reminder, system_reminder

# ASCII 猫图案
CAT_BANNER = r"""  /\_/\
 ( o.o )
  > ^ <"""


def assemble_system(mods: list[Module]) -> str:
    """按 priority 升序、跳过空 content、以双换行连接。"""
    ordered = sorted(mods, key=lambda m: m.priority)
    non_empty = [m.content for m in ordered if m.content]
    return "\n\n".join(non_empty)


def build_system_prompt(instructions: str = "", memory: str = "") -> str:
    """装配完整稳定系统提示（固定模块 + 可选模块）。"""
    return assemble_system(fixed_modules() + optional_modules(instructions, memory))


def render_banner(version: str, cwd: str) -> str:
    """拼出启动横幅：猫 + 应用名与版本 + 工作目录 + 就绪提示行。"""
    return (
        f"{CAT_BANNER}\nMiCodeAgent v{version}\n工作目录: {cwd}\n已就绪，输入 /help 查看可用命令。"
    )


__all__ = [
    "Module",
    "fixed_modules",
    "optional_modules",
    "assemble_system",
    "build_system_prompt",
    "Environment",
    "gather_environment",
    "system_reminder",
    "plan_reminder",
    "EXECUTE_DIRECTIVE",
    "CAT_BANNER",
    "render_banner",
]
