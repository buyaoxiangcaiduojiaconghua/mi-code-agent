"""slash 输入解析"""

from __future__ import annotations


def parse(input_text: str) -> tuple[str, bool]:
    """解析 slash 输入，返回 (命令名, 是否为 slash 命令)。"""
    text = input_text.strip()
    if not text.startswith("/"):
        return ("", False)
    if text == "/":
        return ("", True)
    rest = text[1:]
    # 若有参数（第二段非空），返回空名让 lookup miss
    parts = rest.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        return ("", True)
    return (parts[0].lower(), True)
