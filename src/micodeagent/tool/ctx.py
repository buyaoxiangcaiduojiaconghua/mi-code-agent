"""工具工作目录上下文"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_ctx_cwd: ContextVar[str | None] = ContextVar("cwd", default=None)


@contextmanager
def with_cwd(directory: str):
    """在指定目录上下文内执行。"""
    if not directory:
        yield
        return
    token = _ctx_cwd.set(directory)
    try:
        yield
    finally:
        _ctx_cwd.reset(token)


def cwd_from_ctx() -> str | None:
    return _ctx_cwd.get()


def resolve_path(p: str) -> str:
    """把相对路径解析到当前 ctx 的 cwd 下。"""
    base = _ctx_cwd.get() or str(Path.cwd())
    if not p:
        return base
    if Path(p).is_absolute():
        return str(Path(p))
    return str(Path(base) / p)
