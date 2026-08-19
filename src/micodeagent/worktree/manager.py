"""Worktree 管理器"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from micodeagent.worktree.git import _has_worktree_changes, _resolve_head_sha_from_fs, _run_git
from micodeagent.worktree.session import load_session, save_session
from micodeagent.worktree.slug import flat_slug, validate_slug

DEFAULT_SYMLINK_DIRS = ["node_modules", ".venv", "vendor"]
EPHEMERAL_PATTERN = re.compile(r"^agent-a[0-9a-f]{7}$")


@dataclass
class Worktree:
    name: str
    path: str
    branch: str
    based_on: str
    head_commit: str
    created: datetime
    manual: bool


class WorktreeHasChangesError(Exception):
    pass


class Manager:
    """Worktree 管理器。"""

    def __init__(self, repo_root: str):
        self.repo_root = str(Path(repo_root).resolve())
        result = subprocess.run(
            ["git", "-C", repo_root, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        toplevel = result.stdout.strip()
        if result.returncode != 0 or Path(toplevel).resolve() != Path(self.repo_root):
            raise ValueError("not a git repo root")

        self.worktree_dir = str(Path(repo_root) / ".micodeagent" / "worktrees")
        self.session_file = str(Path(repo_root) / ".micodeagent" / "worktree_session.json")
        self.symlink_dirs = list(DEFAULT_SYMLINK_DIRS)
        self.active: dict[str, Worktree] = {}
        self.current_session = None
        self.lock = asyncio.Lock()

        Path(self.worktree_dir).mkdir(parents=True, exist_ok=True)

        session = load_session(Path(self.session_file))
        if session is not None and not Path(session.worktree_path).exists():
            print("worktree: session path gone, clearing", file=sys.stderr)
            session = None
        self.current_session = session

        # 快速恢复：扫描目录填 active
        for sub in Path(self.worktree_dir).iterdir():
            if not sub.is_dir():
                continue
            sha = _resolve_head_sha_from_fs(str(sub))
            if sha:
                self.active[sub.name] = Worktree(
                    name=sub.name,
                    path=str(sub),
                    branch=f"worktree-{sub.name}",
                    based_on="HEAD",
                    head_commit=sha,
                    created=datetime.now(),
                    manual=False,
                )

    def list(self) -> list[Worktree]:
        return sorted(self.active.values(), key=lambda w: w.name)

    def get(self, name: str) -> Worktree | None:
        return self.active.get(name)

    def current_session(self) -> object:
        return self.current_session

    async def create(self, name: str, base_ref: str, manual: bool) -> Worktree:
        validate_slug(name)
        async with self.lock:
            if name in self.active:
                raise ValueError(f"worktree exists: {name}")
            flat = flat_slug(name)
            wt_path = str(Path(self.worktree_dir) / flat)
            branch = f"worktree-{flat}"

            if Path(wt_path).exists():
                sha = _resolve_head_sha_from_fs(wt_path)
                wt = Worktree(
                    name=name,
                    path=wt_path,
                    branch=branch,
                    based_on=base_ref,
                    head_commit=sha or "",
                    created=datetime.now(),
                    manual=manual,
                )
                self.active[name] = wt
                return wt

            try:
                await _run_git(self.repo_root, "worktree", "add", "-B", branch, wt_path, base_ref)
            except Exception:
                shutil.rmtree(wt_path, ignore_errors=True)
                raise

            await _perform_post_creation_setup(self.repo_root, wt_path, self.symlink_dirs)

            head_sha = await _run_git(wt_path, "rev-parse", "HEAD")
            wt = Worktree(
                name=name,
                path=wt_path,
                branch=branch,
                based_on=base_ref,
                head_commit=head_sha,
                created=datetime.now(),
                manual=manual,
            )
            self.active[name] = wt
            return wt

    async def enter(self, name: str) -> object:
        async with self.lock:
            wt = self.active.get(name)
            if wt is None:
                raise ValueError(f"unknown worktree: {name}")
            original_cwd = str(Path.cwd())
            try:
                original_branch = await _run_git(
                    self.repo_root, "rev-parse", "--abbrev-ref", "HEAD"
                )
                original_head = await _run_git(self.repo_root, "rev-parse", "HEAD")
            except Exception:
                original_branch = ""
                original_head = ""
            session_id = secrets.token_hex(8)
            from micodeagent.worktree.session import WorktreeSession

            session = WorktreeSession(
                worktree_name=name,
                worktree_path=wt.path,
                original_cwd=original_cwd,
                original_branch=original_branch,
                original_head=original_head,
                session_id=session_id,
            )
            self.current_session = session
            save_session(Path(self.session_file), session)
            return session

    async def exit(self, name: str, remove: bool = False, discard_changes: bool = False):
        async with self.lock:
            session = self.current_session
            if session is None or session.worktree_name != name:
                raise ValueError("not in this worktree")
            wt = self.active.get(name)
            if wt is None:
                raise ValueError(f"unknown worktree: {name}")

            if remove and not discard_changes:
                if await _has_worktree_changes(wt.path, wt.head_commit):
                    raise WorktreeHasChangesError(f"worktree {name} has changes")

            if remove:
                try:
                    await _run_git(self.repo_root, "worktree", "remove", "--force", wt.path)
                except Exception:
                    pass
                try:
                    await _run_git(self.repo_root, "branch", "-D", wt.branch)
                except Exception:
                    pass
                self.active.pop(name, None)

            self.current_session = None
            save_session(Path(self.session_file), None)
            return {"removed": remove, "path": wt.path, "branch": wt.branch}

    async def remove(self, name: str, discard_changes: bool = False):
        async with self.lock:
            wt = self.active.get(name)
            if wt is None:
                raise ValueError(f"unknown worktree: {name}")
            if not discard_changes and await _has_worktree_changes(wt.path, wt.head_commit):
                raise WorktreeHasChangesError(f"worktree {name} has changes")
            try:
                await _run_git(self.repo_root, "worktree", "remove", "--force", wt.path)
            except Exception:
                pass
            try:
                await _run_git(self.repo_root, "branch", "-D", wt.branch)
            except Exception:
                pass
            self.active.pop(name, None)
            return {"removed": True, "path": wt.path, "branch": wt.branch}

    async def auto_cleanup(self, name: str) -> dict:
        wt = self.active.get(name)
        if wt is None:
            return {"kept": False}
        if wt.manual:
            return {"kept": True, "path": wt.path, "branch": wt.branch}
        if await _has_worktree_changes(wt.path, wt.head_commit):
            return {"kept": True, "path": wt.path, "branch": wt.branch}
        await self.remove(name, discard_changes=True)
        return {"kept": False}

    async def sweep_stale(self, cutoff: datetime) -> list[str]:
        removed = []
        for sub in Path(self.worktree_dir).iterdir():
            if not sub.is_dir() or not EPHEMERAL_PATTERN.match(sub.name):
                continue
            mtime = datetime.fromtimestamp(sub.stat().st_mtime)
            if mtime > cutoff:
                continue
            if self.current_session and self.current_session.worktree_path == str(sub):
                continue
            if await _has_worktree_changes(str(sub), "HEAD"):
                continue
            try:
                await self.remove(sub.name, discard_changes=True)
                removed.append(sub.name)
            except Exception:
                pass
        return removed


async def _perform_post_creation_setup(
    repo_root: str, wt_path: str, symlink_dirs: list[str]
) -> None:
    steps = [
        ("config", lambda: _copy_local_configs(repo_root, wt_path)),
        ("hooks", lambda: _setup_git_hooks(repo_root, wt_path)),
        ("symlink", lambda: _symlink_large_dirs(repo_root, wt_path, symlink_dirs)),
        ("include", lambda: _copy_included_ignored(repo_root, wt_path)),
    ]
    for step_name, fn in steps:
        try:
            fn()
        except Exception as e:
            print(f"worktree: setup {step_name}: {e}", file=sys.stderr)


def _copy_local_configs(repo_root: str, wt_path: str) -> None:
    for name in [".micodeagent/config.yaml", ".micodeagent/settings.local.yaml"]:
        src = Path(repo_root) / name
        dst = Path(wt_path) / name
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)


def _setup_git_hooks(repo_root: str, wt_path: str) -> None:
    hooks_path = Path(repo_root) / ".husky"
    if not hooks_path.exists():
        r = subprocess.run(
            ["git", "-C", repo_root, "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
        )
        hooks_path = Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    if hooks_path:
        subprocess.run(["git", "-C", wt_path, "config", "core.hooksPath", str(hooks_path)])


def _symlink_large_dirs(repo_root: str, wt_path: str, symlink_dirs: list[str]) -> None:
    for d in symlink_dirs:
        src = Path(repo_root) / d
        dst = Path(wt_path) / d
        if src.exists() and not dst.exists():
            os.symlink(src, dst)


def _copy_included_ignored(repo_root: str, wt_path: str) -> None:
    include_file = Path(repo_root) / ".worktreeinclude"
    if not include_file.exists():
        return
    import fnmatch

    patterns = [line.strip() for line in include_file.read_text().splitlines() if line.strip()]
    if not patterns:
        return
    r = subprocess.run(
        ["git", "-C", repo_root, "ls-files", "--others", "--ignored", "--exclude-standard"],
        capture_output=True,
        text=True,
    )
    for line in r.stdout.splitlines():
        if any(fnmatch.fnmatch(line, p) for p in patterns):
            src = Path(repo_root) / line
            dst = Path(wt_path) / line
            if src.is_file() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dst)


def random_agent_name() -> str:
    return "agent-a" + secrets.token_hex(4)[:7]
