"""按模式找文件工具（Glob）"""

import asyncio
import json
from pathlib import Path

from micodeagent.tool import Result
from micodeagent.tool.ctx import resolve_path


class GlobTool:
    """按模式找文件——用 glob 模式匹配文件路径。"""

    read_only = True

    def name(self) -> str:
        return "glob"

    def description(self) -> str:
        return (
            "根据文件名模式在指定目录下搜索匹配的文件。"
            "使用 glob 模式匹配，支持通配符 **（递归）、*（任意字符）、?（单个字符）。"
            "例如 '**/*.py' 查找所有 Python 文件。"
            "返回匹配的文件路径列表（最多 100 条）。"
        )

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "glob 匹配模式，如 '**/*.py'",
                },
                "path": {
                    "type": "string",
                    "description": "搜索根目录，默认 '.'",
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

        try:
            if not root.exists():
                return Result(content=f"目录不存在: {root}", is_error=True)
            if not root.is_dir():
                return Result(content=f"路径不是目录: {root}", is_error=True)

            matches = []
            for p in root.glob(pattern):
                if p.is_file():
                    matches.append(str(p))
                if len(matches) >= 100:
                    break
                # 每 100 个让出 event loop
                if len(matches) % 100 == 0:
                    await asyncio.sleep(0)

            matches.sort()
            if not matches:
                return Result(content="无匹配")
            return Result(content=f"找到 {len(matches)} 个匹配的文件:\n" + "\n".join(matches))
        except Exception as e:
            return Result(content=f"搜索文件异常: {e}", is_error=True)
