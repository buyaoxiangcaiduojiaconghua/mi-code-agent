"""执行命令工具（Bash）"""

import asyncio
import json

from micodeagent.tool import Result, _truncate


class BashTool:
    """执行命令——在 shell 中运行命令，返回 stdout/stderr/退出码。"""

    read_only = False

    def name(self) -> str:
        return "bash"

    def description(self) -> str:
        return (
            "执行一个 shell 命令并返回输出结果。"
            "命令在隔离的子进程中运行，带超时保护。"
            "返回 stdout、stderr 与退出码。"
            "⚠️ 仅当没有专用工具时才用此工具。"
            "读写文件请用 read_file/write_file/edit_file，"
            "搜索文件请用 glob，搜索代码内容请用 grep。"
            "⚠️ 读文件、找文件、搜内容请优先用 read_file/glob/grep，不要用 bash 拼凑替代。"
        )

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令",
                },
            },
            "required": ["command"],
        }

    async def execute(self, args: str) -> Result:
        try:
            data = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            return Result(content="参数 JSON 解析失败", is_error=True)

        command = data.get("command", "")
        if not command:
            return Result(content="缺少必填参数: command", is_error=True)

        try:
            from micodeagent.tool.ctx import resolve_path

            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=resolve_path(""),
            )
            stdout_bytes, stderr_bytes = await proc.communicate()
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            parts = [f"exit_code: {proc.returncode}"]
            if stdout:
                parts.append(f"stdout:\n{stdout}")
            if stderr:
                parts.append(f"stderr:\n{stderr}")

            content = _truncate("\n".join(parts), max_lines=10000, max_chars=30000)
            return Result(content=content)
        except FileNotFoundError:
            return Result(
                content=f"命令不存在: {command.split()[0] if command else command}",
                is_error=True,
            )
        except Exception as e:
            return Result(content=f"命令执行异常: {e}", is_error=True)
