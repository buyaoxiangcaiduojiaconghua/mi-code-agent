"""三段恢复：文件快照 + 工具列表 + 边界提示"""

from __future__ import annotations

import json

from micodeagent.compact.const import (
    ESTIMATE_CHARS_PER_TOKEN,
    RECOVERY_FILE_LIMIT,
    RECOVERY_TOKENS_PER_FILE,
)
from micodeagent.compact.state import FileReadRecord
from micodeagent.llm import ToolDefinition

BOUNDARY_NOTICE = (
    "需要文件原文、错误原文、用户原话时，请使用文件读取工具重新读取对应路径。"
    "不要依据摘要内容做猜测，所有代码细节以磁盘文件为准。"
)


def render_file_block(rec: FileReadRecord) -> str:
    """渲染单个文件快照。"""
    char_limit = int(RECOVERY_TOKENS_PER_FILE * ESTIMATE_CHARS_PER_TOKEN)
    content = rec.content
    truncated = ""
    if len(content) > char_limit:
        content = content[:char_limit]
        truncated = "\n(content truncated)"
    return f"### {rec.path}\n[read at] {rec.timestamp.isoformat()}\n{content}{truncated}\n"


def render_tools_block(defs: list[ToolDefinition]) -> str:
    """渲染工具列表。"""
    lines = []
    for d in defs:
        schema = json.dumps(d.input_schema, separators=(",", ":"), ensure_ascii=False)
        lines.append(f"- {d.name}: {d.description}")
        lines.append(f"  schema: {schema}")
    return "\n".join(lines)


def build_recovery_attachment(
    snapshot: list[FileReadRecord],
    tool_defs: list[ToolDefinition],
) -> str:
    """构造摘要后的恢复三段内容。"""
    parts = []

    # 1. 最近读过的文件
    parts.append("## 最近读过的文件\n")
    recent = snapshot[:RECOVERY_FILE_LIMIT]
    if recent:
        for rec in recent:
            parts.append(render_file_block(rec))
    else:
        parts.append("(无)\n")

    # 2. 当前可用工具
    parts.append("## 当前可用工具\n")
    parts.append(render_tools_block(tool_defs))
    parts.append("")

    # 3. 边界提示
    parts.append("## 边界提示\n")
    parts.append(BOUNDARY_NOTICE)

    return "\n".join(parts)
