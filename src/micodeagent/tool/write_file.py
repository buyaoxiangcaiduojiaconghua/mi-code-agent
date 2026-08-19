"""写文件工具"""

import json
from pathlib import Path

from micodeagent.tool import Result
from micodeagent.tool.ctx import resolve_path


class WriteFileTool:
    """写文件——创建或覆盖文件，父目录自动创建。"""

    read_only = False

    def name(self) -> str:
        return "write_file"

    def description(self) -> str:
        return (
            "创建新文件或覆盖已有文件。"
            "传入文件路径和要写入的内容，如果父目录不存在会自动创建。"
            "注意：这会覆盖已有文件的所有内容。"
        )

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "要写入的内容"},
            },
            "required": ["path", "content"],
        }

    async def execute(self, args: str) -> Result:
        try:
            data = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            return Result(content="参数 JSON 解析失败", is_error=True)

        path = data.get("path", "")
        content = data.get("content", "")
        if not path:
            return Result(content="缺少必填参数: path", is_error=True)

        try:
            file_path = Path(resolve_path(path))
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            size = len(content.encode("utf-8"))
            return Result(content=f"已写入 {path}（{size} 字节）")
        except PermissionError:
            return Result(content=f"没有权限写入: {path}", is_error=True)
        except OSError as e:
            return Result(content=f"写入文件失败: {e}", is_error=True)
        except Exception as e:
            return Result(content=f"写入文件异常: {e}", is_error=True)
