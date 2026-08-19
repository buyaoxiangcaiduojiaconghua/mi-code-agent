"""改文件工具——原文唯一匹配替换"""

import json
from pathlib import Path

from micodeagent.tool import Result
from micodeagent.tool.ctx import resolve_path


class EditFileTool:
    """改文件——对原文片段做唯一匹配替换。"""

    read_only = False

    def name(self) -> str:
        return "edit_file"

    def description(self) -> str:
        return (
            "修改文件中指定的文本片段。"
            "通过原文匹配的方式精确替换：传入要修改的原文（old_string）和新内容（new_string），"
            "工具会在文件中找到唯一匹配的 old_string 并替换为 new_string。"
            "原文必须精确匹配（包括空格、换行、缩进），且在文件中只能出现一次。"
            "old_string 不匹配或匹配多次时会报错，请先读文件确认内容后再调用。"
            "⚠️ 编辑前请先用 read_file 读取目标文件，确认 old_string 唯一。"
        )

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "old_string": {"type": "string", "description": "要被替换的原文"},
                "new_string": {"type": "string", "description": "替换后的新内容"},
            },
            "required": ["path", "old_string", "new_string"],
        }

    async def execute(self, args: str) -> Result:
        try:
            data = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            return Result(content="参数 JSON 解析失败", is_error=True)

        path = data.get("path", "")
        old = data.get("old_string", "")
        new = data.get("new_string", "")
        if not path or not old:
            return Result(content="缺少必填参数: path 或 old_string", is_error=True)

        try:
            file_path = Path(resolve_path(path))
            if not file_path.exists():
                return Result(content=f"文件不存在: {path}", is_error=True)
            if not file_path.is_file():
                return Result(content=f"路径不是文件: {path}", is_error=True)

            original = file_path.read_text(encoding="utf-8")
            n = original.count(old)
            if n == 0:
                return Result(content="未找到匹配的内容", is_error=True)
            if n > 1:
                return Result(
                    content=f"匹配到 {n} 处，old_string 不唯一，请提供更长上下文使其唯一",
                    is_error=True,
                )

            new_content = original.replace(old, new, 1)
            file_path.write_text(new_content, encoding="utf-8")
            return Result(content=f"文件已修改: {path}")
        except PermissionError:
            return Result(content=f"没有权限修改: {path}", is_error=True)
        except UnicodeDecodeError:
            return Result(content=f"无法以 UTF-8 编码读取: {path}", is_error=True)
        except Exception as e:
            return Result(content=f"编辑文件异常: {e}", is_error=True)
