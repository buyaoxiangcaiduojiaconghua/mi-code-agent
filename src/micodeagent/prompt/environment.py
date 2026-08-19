"""环境信息采集与渲染

收集运行环境（工作目录、平台、日期、git 状态等），渲染为独立文本段。
"""

import datetime
import os
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class Environment:
    """运行环境信息"""

    working_dir: str  # os.getcwd()
    platform: str  # sys.platform
    date: str  # 当前日期
    git_status: str  # git status 摘要；非 git 目录/取不到则留空
    version: str  # 应用版本
    model: str  # 当前模型

    def render(self) -> str:
        """渲染为「环境信息」文本段，逐行 Key: Value，空值项省略。"""
        lines = [
            f"Working directory: {self.working_dir}",
            f"Platform: {self.platform}",
            f"Date: {self.date}",
        ]
        if self.git_status:
            lines.append(f"Git status: {self.git_status}")
        lines.append(f"MiCodeAgent version: {self.version}")
        lines.append(f"Model: {self.model}")
        return "\n".join(lines)


def gather_environment(version: str, model: str) -> Environment:
    """采集运行环境，各项失败时降级留空。"""
    # 工作目录
    try:
        working_dir = os.getcwd()
    except OSError:
        working_dir = ""

    # 平台
    platform_str = sys.platform

    # 日期
    date_str = datetime.date.today().isoformat()

    # git 状态（2s 超时，失败降级为空）
    git_status = ""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            if len(lines) <= 10:
                git_status = result.stdout.strip()
            else:
                git_status = f"{len(lines)} 个文件有改动"
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
        OSError,
        ValueError,
    ):
        git_status = ""

    return Environment(
        working_dir=working_dir,
        platform=platform_str,
        date=date_str,
        git_status=git_status,
        version=version,
        model=model,
    )
