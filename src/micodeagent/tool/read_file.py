"""读文件工具"""

import json
from pathlib import Path

from micodeagent.tool import Result, _truncate
from micodeagent.tool.ctx import resolve_path


class ReadFileTool:
    """读文件——返回带行号的文本内容。"""

    read_only = True

    def name(self) -> str:
        return "read_file"

    def description(self) -> str:
        return (
            "读取指定路径的文件内容。"
            "返回带行号的完整文本，方便引用具体行。"
            "文件不存在或不可读时返回结构化错误。"
        )

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要读取的文件路径",
                },
            },
            "required": ["path"],
        }

    async def execute(self, args: str) -> Result:
        try:
            data = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            return Result(content="参数 JSON 解析失败", is_error=True)

        path = data.get("path", "")
        if not path:
            return Result(content="缺少必填参数: path", is_error=True)

        try:
            file_path = Path(resolve_path(path))
            if not file_path.exists():
                return Result(content=f"文件不存在: {path}", is_error=True)
            if file_path.is_dir():
                return Result(content=f"路径是目录而非文件: {path}", is_error=True)

            text = file_path.read_text(encoding="utf-8")
            lines = text.split("\n")
            numbered = []
            for i, line in enumerate(lines, 1):
                numbered.append(f"{i:6d}\t{line}")

            content = _truncate("\n".join(numbered), max_lines=2000, max_chars=256 * 1024)
            return Result(content=content)
        except PermissionError:
            return Result(content=f"没有权限读取: {path}", is_error=True)
        except UnicodeDecodeError:
            return Result(content=f"无法以 UTF-8 编码读取: {path}", is_error=True)
        except Exception as e:
            return Result(content=f"读取文件异常: {e}", is_error=True)
