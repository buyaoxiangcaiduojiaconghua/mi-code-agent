"""L1: 危险命令黑名单

内置正则匹配已知高危命令，不可配置绕过。
启发式防御，非完备保证。
"""

import re

_BLACKLIST: list[re.Pattern] = [
    re.compile(r"rm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+(/|~|\$HOME|/\*)"),
    re.compile(r"rm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+\.\."),
    re.compile(r"dd\s+.*of=/dev/"),
    re.compile(r":\(\)\s*\{.*\|.*&\s*\}", re.DOTALL),  # fork bomb
    re.compile(r"mkfs\."),
    re.compile(r">\s*/dev/(sd|hd|nvme|disk)"),
    re.compile(r"chmod\s+-R\s+0?777\s+/"),
    re.compile(r"curl.*\|\s*(ba)?sh"),
    re.compile(r"wget.*\|\s*(ba)?sh"),
    re.compile(r"sudo\s+rm"),
]


def hits_blacklist(command: str) -> bool:
    """检查命令是否命中黑名单"""
    return any(p.search(command) for p in _BLACKLIST)
