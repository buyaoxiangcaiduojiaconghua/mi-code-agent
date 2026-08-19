"""L4: 权限引擎——前四层统一入口"""

import logging
from dataclasses import dataclass
from pathlib import Path

from micodeagent.llm import ToolCall
from micodeagent.permission import Category, Decision, Mode, parse_mode
from micodeagent.permission.blacklist import hits_blacklist
from micodeagent.permission.rule import RuleSet
from micodeagent.permission.sandbox import resolve_root, sandbox_ok
from micodeagent.permission.settings import (
    SettingsError,
    categorize,
    extract_target,
    friendly_name,
    load_settings,
    to_rule_set,
)

logger = logging.getLogger(__name__)


def mode_fallback(mode: Mode, cat: Category) -> Decision:
    """F5 矩阵：模式兜底裁决（只产 Allow/Ask）。"""
    if cat == Category.READ or mode == Mode.BYPASS:
        return Decision.ALLOW
    if mode == Mode.ACCEPT_EDITS and cat == Category.WRITE:
        return Decision.ALLOW
    return Decision.ASK


@dataclass
class Engine:
    """权限引擎"""

    root: str
    user: RuleSet
    project: RuleSet
    local: RuleSet
    local_path: str
    start_mode: Mode

    def check(self, mode: Mode, call: ToolCall, read_only: bool) -> tuple[Decision, str]:
        """前四层判定流水线"""
        cat = categorize(call.name, read_only)
        friendly = friendly_name(call.name)
        target, is_file, ok = extract_target(call)

        # ① 黑名单（仅 Exec 类）
        if cat == Category.EXEC and target and hits_blacklist(target):
            return (Decision.DENY, f"命中危险命令黑名单：{target[:80]}")

        # ② 沙箱（仅文件类）
        if is_file:
            if not ok:
                return (Decision.DENY, "无法解析文件路径参数，安全拒绝")
            if not sandbox_ok(self.root, target):
                return (Decision.DENY, f"路径在项目目录之外：{target}")

        # ③ 规则引擎：local → project → user
        for ruleset, label in [
            (self.local, "本地规则"),
            (self.project, "项目规则"),
            (self.user, "用户规则"),
        ]:
            dec, hit = ruleset.match(friendly, target)
            if hit:
                if dec == Decision.DENY:
                    return (dec, f"匹配 deny 规则（{label}）：{friendly}（{target[:80]}）")
                return (dec, "")

        # ④ 模式兜底
        fallback = mode_fallback(mode, cat)
        if fallback == Decision.ALLOW:
            return (Decision.ALLOW, "")
        cat_name = {Category.READ: "只读", Category.WRITE: "文件写", Category.EXEC: "命令执行"}[cat]
        return (Decision.ASK, f"{mode} 模式下 {cat_name} 类操作需确认")


def new_engine(root: str) -> tuple[Engine, Exception | None]:
    """构造权限引擎，加载三层配置"""
    err = None
    try:
        root = resolve_root(root)
    except Exception as e:
        err = e
        root = root  # 退化使用传入值

    home = Path.home()
    user_path = str(home / ".micodeagent" / "settings.yaml")
    project_path = str(Path(root) / ".micodeagent" / "settings.yaml")
    local_path = str(Path(root) / ".micodeagent" / "settings.local.yaml")

    user_rules = _load_or_empty(user_path)
    project_rules = _load_or_empty(project_path)
    local_rules = _load_or_empty(local_path)

    # 确定启动模式：local > project > user
    start_mode = Mode.DEFAULT
    for path in [local_path, project_path, user_path]:
        try:
            s = load_settings(path)
            if s.default_mode:
                m, ok = parse_mode(s.default_mode)
                if ok:
                    start_mode = m
                    break
        except SettingsError:
            pass

    engine = Engine(
        root=root,
        user=user_rules,
        project=project_rules,
        local=local_rules,
        local_path=local_path,
        start_mode=start_mode,
    )
    return (engine, err)


def _load_or_empty(path: str) -> RuleSet:
    try:
        return to_rule_set(load_settings(path))
    except SettingsError:
        return RuleSet()
