"""权限 Matcher：四种匹配类型"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from typing import Protocol


class Matcher(Protocol):
    def match(self, s: str) -> bool: ...

    def __str__(self) -> str: ...


@dataclass(frozen=True)
class ExactMatcher:
    """精确匹配。"""

    value: str

    def match(self, s: str) -> bool:
        return s == self.value

    def __str__(self) -> str:
        return f"={self.value}"


@dataclass(frozen=True)
class GlobMatcher:
    """glob 匹配（命令或路径）。"""

    pattern: str
    is_command: bool

    def match(self, s: str) -> bool:
        if self.is_command:
            return self._match_command(s)
        return self._match_path(s)

    def _match_command(self, s: str) -> bool:
        # 命令 glob：* 匹配任意字符（含空格）
        return fnmatch.fnmatch(s, self.pattern)

    def _match_path(self, s: str) -> bool:
        # 路径 glob：fnmatch 标准匹配（* 段内、** 跨段由 pathlib 语义近似）
        return fnmatch.fnmatch(s, self.pattern)

    def __str__(self) -> str:
        return self.pattern


@dataclass(frozen=True)
class RegexMatcher:
    """正则匹配。"""

    src: str
    compiled: re.Pattern[str]

    def match(self, s: str) -> bool:
        return self.compiled.search(s) is not None

    def __str__(self) -> str:
        return f"~{self.src}"


@dataclass(frozen=True)
class NotMatcher:
    """反向匹配。"""

    inner: Matcher

    def match(self, s: str) -> bool:
        return not self.inner.match(s)

    def __str__(self) -> str:
        return f"!{self.inner}"


def compile_matcher(pattern: str, *, is_command: bool) -> Matcher:
    """按前缀编译 matcher：= 精确、~ 正则、! 反向、其它 glob。"""
    if not pattern:
        raise ValueError("empty matcher pattern")
    if pattern.startswith("="):
        return ExactMatcher(pattern[1:])
    if pattern.startswith("~"):
        try:
            return RegexMatcher(pattern[1:], re.compile(pattern[1:]))
        except re.error as e:
            raise ValueError(f"invalid regex: {e}")
    if pattern.startswith("!"):
        inner = compile_matcher(pattern[1:], is_command=is_command)
        return NotMatcher(inner)
    return GlobMatcher(pattern, is_command)
