"""TUI 视图渲染模块

提供状态栏、用户块、错误块、markdown 定型、动态区、
工具行、工具结果摘要与待批准块等纯渲染函数。
"""

from rich.markdown import Markdown
from rich.padding import Padding
from rich.text import Text

from micodeagent.permission import ApprovalRequest, Mode

_MODE_LABELS: dict[Mode, str] = {
    Mode.DEFAULT: "DEFAULT",
    Mode.ACCEPT_EDITS: "ACCEPT EDITS",
    Mode.PLAN: "PLAN",
    Mode.BYPASS: "BYPASS",
}


def _fmt_tok(n: int) -> str:
    """紧凑 token 数字，如 1.2k。"""
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def status_bar(
    mode: Mode,
    model: str,
    usage_in: int = 0,
    usage_out: int = 0,
    width: int = 80,
) -> str:
    """渲染底部状态栏：左侧常驻权限模式，右侧模型名 + 累计用量。"""
    left = f"▌ {_MODE_LABELS.get(mode, '???')}"

    right = model
    if usage_in or usage_out:
        right += f"  ↑{_fmt_tok(usage_in)} ↓{_fmt_tok(usage_out)} tok"

    padding = max(2, width - len(left) - len(right))
    return left + " " * padding + right


def user_block(text: str) -> Text:
    """渲染用户消息块（无 You 文字标签）。"""
    return Text("● " + text, style="bold")


def error_block(err: Exception) -> Text:
    """渲染错误块（红色可区分样式）。"""
    return Text("● " + str(err), style="bold red")


def render_markdown(reply: str) -> Markdown:
    """把整段回复渲染为 markdown，用于流式结束后的定型展示。"""
    return Markdown(reply)


def streaming_view(cur_reply: str, elapsed: int, iter_num: int = 0) -> Text:
    """渲染流式期间的动态区：当前回复 + 进行中计时（附轮次）。"""
    t = Text()
    if cur_reply:
        t.append("● " + cur_reply)
        t.append("\n")
    suffix = f"（第 {iter_num} 轮）" if iter_num > 0 else ""
    t.append(f"Imagining… ({elapsed}s{suffix})", style="dim")
    return t


def tool_line(name: str, args: str) -> Text:
    """渲染工具行：● name(args)，青色加粗。"""
    return Text.assemble(
        ("● ", "bold cyan"),
        (f"{name}({args})", "bold"),
    )


def tool_result_summary(result: str, is_error: bool = False) -> Padding:
    """渲染工具结果摘要：缩进 ⎿、灰/红、截断 ~8 行。"""
    lines = result.split("\n")[:8]
    text = "\n".join(lines)
    if len(result.split("\n")) > 8:
        text += "\n...（已截断）"
    style = "bold red" if is_error else "dim"
    return Padding(Text("⎿ " + text, style=style), (0, 0, 0, 2))


def approval_block(req: ApprovalRequest, cursor: int = 0) -> str:
    """渲染待批准块：工具名 + 参数预览 + 原因 + 三选菜单。"""
    lines: list[str] = []
    lines.append(f"🔒 工具需要审批: [bold]{req.name}[/]")

    args_text = req.args
    if len(args_text) > 80:
        args_text = args_text[:77] + "..."
    lines.append(f"   参数: {args_text}")
    lines.append(f"   原因: {req.reason}")
    lines.append("")

    items = [
        "允许本次",
        "永久允许（写入本地配置）",
        "拒绝本次",
    ]
    for i, title in enumerate(items):
        if i == cursor:
            lines.append(f"  ▶ [bold]{i + 1}. {title}[/]")
        else:
            lines.append(f"    {i + 1}. {title}")

    lines.append("")
    lines.append("[dim]↑↓ 选择 · 回车确认 · 数字键直选 · Esc 取消[/]")
    return "\n".join(lines)
