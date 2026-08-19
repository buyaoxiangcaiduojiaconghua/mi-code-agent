"""Worktree git 辅助"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path


async def _run_git(work_dir: str, *args: str) -> str:
    """运行 git 命令，返回 stdout（去换行）。"""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=work_dir,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())
    return stdout.decode("utf-8", errors="replace").rstrip("\n")


async def _has_worktree_changes(wt_path: str, base_commit: str) -> bool:
    """检查 worktree 是否有未提交修改或未推送 commit。"""
    try:
        status = await _run_git(wt_path, "status", "--porcelain")
        if status.strip():
            return True
        count = await _run_git(wt_path, "rev-list", "--count", f"{base_commit}..HEAD")
        if int(count or 0) > 0:
            return True
        return False
    except Exception:
        return True  # fail-closed


def _resolve_head_sha_from_fs(wt_path: str) -> str | None:
    """从文件系统读 worktree 的 HEAD SHA（快速恢复，不调 git）。"""
    git_file = Path(wt_path) / ".git"
    if not git_file.exists():
        return None
    try:
        content = git_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not content.startswith("gitdir:"):
        return None
    gitdir = content.split(":", 1)[1].strip()
    gitdir_path = Path(gitdir)
    if not gitdir_path.is_absolute():
        gitdir_path = Path(wt_path) / gitdir
    try:
        head = (gitdir_path / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if head.startswith("ref: refs/heads/"):
        ref = head.split(" ", 1)[1]
        ref_path = gitdir_path / ref
        try:
            return ref_path.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return head or None
