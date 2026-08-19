"""L3: 规则引擎

规则格式：Tool(pattern) → allow/deny
支持精确匹配和 glob 匹配。
"""

import fnmatch
from dataclasses import dataclass, field

from micodeagent.permission import Decision


@dataclass
class Rule:
    """单条规则"""

    tool: str  # 友好名：Bash/Read/Write/Edit/Glob/Grep
    pattern: str  # 模式段；"" 表示匹配全部
    allow: bool  # True=allow, False=deny


@dataclass
class RuleSet:
    allow: list[Rule] = field(default_factory=list)
    deny: list[Rule] = field(default_factory=list)

    def match(self, friendly: str, target: str) -> tuple[Decision, bool]:
        """先 deny 再 allow；返回 (Allow|Deny, 命中?)"""
        for r in self.deny:
            if r.tool == friendly and match_pattern(r.pattern, target):
                return (Decision.DENY, True)
        for r in self.allow:
            if r.tool == friendly and match_pattern(r.pattern, target):
                return (Decision.ALLOW, True)
        return (Decision.ALLOW, False)


def parse_rule(s: str) -> tuple[Rule, bool]:
    """解析 "Bash(git *)" 或 "Read" 格式的规则字符串"""
    s = s.strip()
    if not s:
        return (Rule("", "", False), False)

    idx = s.find("(")
    if idx == -1:
        tool = s
        pattern = ""
    else:
        if not s.endswith(")"):
            return (Rule("", "", False), False)
        tool = s[:idx].strip()
        pattern = s[idx + 1 : -1].strip()

    if not tool:
        return (Rule("", "", False), False)

    return (Rule(tool=tool, pattern=pattern, allow=True), True)


def match_pattern(pattern: str, target: str) -> bool:
    """glob 匹配：pattern 为空则全匹配"""
    if not pattern:
        return True
    return fnmatch.fnmatch(target, pattern)
