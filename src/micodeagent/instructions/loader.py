"""项目指令文件加载器

三层加载 MEWCODE.md，支持 @include 引用展开。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_INCLUDE_RE = re.compile(r"^@include\s+(.+)$")


class Loader:
    """加载项目指令文件（三层优先级 + @include 展开）。"""

    def __init__(self, project_root: str, user_home: str | None = None, max_depth: int = 5):
        self.project_root = str(Path(project_root).resolve())
        self.user_home = user_home or os.path.expanduser("~")
        self.max_depth = max_depth

    def load(self) -> str:
        """按优先级扫描三个路径，拼接结果。"""
        # ① 项目级（最高优先级）
        # ② 项目配置级
        # ③ 用户级（最低优先级）
        paths = [
            (Path(self.project_root) / "MEWCODE.md", self.project_root),
            (Path(self.project_root) / ".micodeagent" / "MEWCODE.md", self.project_root),
            (
                Path(self.user_home) / ".micodeagent" / "MEWCODE.md",
                str(Path(self.user_home) / ".micodeagent"),
            ),
        ]
        parts = []
        for path, boundary in paths:
            content = self._load_file(str(path), boundary, depth=1, visited=set())
            if content:
                parts.append(content)
        return "\n\n".join(parts)

    def _load_file(self, path: str, boundary: str, depth: int, visited: set[str]) -> str:
        """加载单个文件，递归展开 @include。"""
        real = os.path.realpath(path)

        if depth > self.max_depth:
            return f"<!-- @include 超过最大嵌套深度，已跳过: {path} -->"

        if real in visited:
            return f"<!-- @include 检测到环路，已跳过: {path} -->"

        # 路径逃逸检测
        try:
            common = os.path.commonpath([real, boundary])
            if common != boundary and not real.startswith(boundary.rstrip(os.sep) + os.sep):
                return f"<!-- @include 路径超出允许范围，已跳过: {path} -->"
        except ValueError:
            return f"<!-- @include 路径超出允许范围，已跳过: {path} -->"

        if not os.path.isfile(real):
            return ""  # 找不到静默跳过

        try:
            with open(real, "rb") as f:
                head = f.read(512)
        except OSError:
            return ""

        if b"\x00" in head:
            return f"<!-- @include 二进制文件，已跳过: {path} -->"

        try:
            with open(real, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return ""

        visited.add(real)

        lines = content.split("\n")
        out_lines = []
        for line in lines:
            m = _INCLUDE_RE.match(line.strip())
            if m:
                include_path = m.group(1).strip()
                resolved = os.path.join(os.path.dirname(real), include_path)
                expanded = self._load_file(resolved, boundary, depth + 1, visited)
                out_lines.append(expanded)
            else:
                out_lines.append(line)

        visited.discard(real)
        return "\n".join(out_lines)
