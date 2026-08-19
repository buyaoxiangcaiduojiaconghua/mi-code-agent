"""补充消息注入与规划模式提醒

提供 <system-reminder> 标签包裹、规划模式提醒（完整/精简）与执行指令。
"""

# 规划模式完整提醒
_PLAN_REMINDER_FULL = (
    "You are currently in PLAN MODE. You may use ONLY the read-only tools "
    "(read_file, glob, grep) to investigate the codebase. You must NOT write files, "
    "edit files, or run shell commands. "
    "Produce a clear, step-by-step plan for the task, "
    "then stop and wait for the user to approve it with /do before doing any work."
)

# 规划模式精简提醒
_PLAN_REMINDER_CONCISE = "（提醒：你仍在 Plan Mode 中，只能使用只读工具，不要修改文件。）"

# /do 注入的用户消息
EXECUTE_DIRECTIVE = "请按上面的计划开始执行。"


def system_reminder(body: str) -> str:
    """用 <system-reminder> 标签包裹补充指令。"""
    return f"<system-reminder>\n{body}\n</system-reminder>"


def plan_reminder(full: bool) -> str:
    """返回带标签的规划模式提醒（full=True 完整版，否则精简版）。"""
    return system_reminder(_PLAN_REMINDER_FULL if full else _PLAN_REMINDER_CONCISE)
