"""搜代码内容工具（Grep）"""

import asyncio
import json
import re
from pathlib import Path

from micodeagent.tool import Result
from micodeagent.tool.ctx import resolve_path


class GrepTool:
    """搜代码内容——用正则匹配文件中的文本。"""

    read_only = True

    def name(self) -> str:
        return "grep"

    def description(self) -> str:
        return (
            "在指定目录下的文件中搜索匹配的文本内容。"
            "支持 Python 正则表达式搜索。"
            "返回匹配的行，格式为 '文件路径:行号: 行内容'。"
            "可以用 file_pattern 限制搜索的文件类型。"
            "如已知目标文件路径，优先用 read_file 直接读取。"
        )

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "搜索文本或 Python 正则表达式",
                },
                "path": {
                    "type": "string",
                    "description": "搜索根目录，默认 '.'",
                },
                "glob": {
                    "type": "string",
                    "description": "文件类型过滤，如 '*.py'",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, args: str) -> Result:
        try:
            data = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            return Result(content="参数 JSON 解析失败", is_error=True)

        pattern = data.get("pattern", "")
        if not pattern:
            return Result(content="缺少必填参数: pattern", is_error=True)

        root = Path(resolve_path(data.get("path") or "."))
        file_filter = data.get("glob") or "*"

        try:
            rx = re.compile(pattern)
        except re.error as e:
            return Result(content=f"正则非法: {e}", is_error=True)

        try:
            if not root.exists():
                return Result(content=f"目录不存在: {root}", is_error=True)
            if not root.is_dir():
                return Result(content=f"路径不是目录: {root}", is_error=True)

            results = []
            for file_path in root.glob(f"**/{file_filter}"):
                if not file_path.is_file():
                    continue
                try:
                    # 跳过超大文件
                    if file_path.stat().st_size > 1024 * 1024:
                        continue
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except (OSError, PermissionError):
                    continue

                for line_no, line in enumerate(content.splitlines(), 1):
                    if rx.search(line):
                        results.append(f"{file_path}:{line_no}: {line.strip()[:200]}")
                        if len(results) >= 100:
                            break
                if len(results) >= 100:
                    break
                # 每处理完一个文件让出 event loop
                await asyncio.sleep(0)

            if not results:
                return Result(content="无命中")
            return Result(content=f"找到 {len(results)} 处匹配:\n" + "\n".join(results))
        except Exception as e:
            return Result(content=f"搜索代码异常: {e}", is_error=True)
