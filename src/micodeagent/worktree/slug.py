"""Worktree slug 校验"""

from __future__ import annotations

import re

_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def validate_slug(name: str) -> None:
    """校验 worktree slug，失败抛 ValueError。"""
    if not name:
        raise ValueError("empty slug")
    if len(name) > 64:
        raise ValueError("slug too long (>64)")
    if name.startswith("/") or name.endswith("/"):
        raise ValueError("slug must not start/end with /")
    if "//" in name:
        raise ValueError("slug must not contain consecutive /")
    for segment in name.split("/"):
        if not segment or segment in (".", ".."):
            raise ValueError(f"invalid slug segment: {segment!r}")
        if not _SEGMENT_RE.match(segment):
            raise ValueError(f"invalid slug segment: {segment!r}")


def flat_slug(name: str) -> str:
    """把嵌套 slug 扁平化（/ 换成 +）。"""
    return name.replace("/", "+")
