"""Hook 规则加载器：YAML 解析 + 双层合并 + 校验"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from micodeagent.hook.engine import Engine
from micodeagent.hook.event import is_blocking, parse_event
from micodeagent.hook.rule import (
    Action,
    ActionType,
    AtomCondition,
    CombineMode,
    Condition,
    HttpAction,
    PromptAction,
    Rule,
    ShellAction,
    SubagentAction,
)
from micodeagent.permission.matcher import compile_matcher

_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)([smh]?)$")


def _parse_duration(s: str) -> float:
    m = _DURATION_RE.match(str(s).strip())
    if not m:
        raise ValueError(f"invalid duration: {s}")
    value = float(m.group(1))
    unit = m.group(2)
    if unit == "m":
        return value * 60
    if unit == "h":
        return value * 3600
    return value


def load(project_root: str | Path) -> Engine:
    """加载两层 hooks.yaml，返回 Engine。"""
    root = str(project_root)
    paths = [
        str(Path(root) / ".micodeagent" / "hooks.yaml"),
        str(Path.home() / ".micodeagent" / "hooks.yaml"),
    ]
    rules: list[Rule] = []
    sources: list[str] = []
    seen_names: set[str] = set()

    for path in paths:
        if not Path(path).exists():
            continue
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as e:
            print(f"hook: load {path} failed: {e}", file=sys.stderr)
            continue
        if not isinstance(data, dict) or not isinstance(data.get("hooks"), list):
            print(f"hook: invalid structure in {path}, skipped", file=sys.stderr)
            continue
        for idx, raw in enumerate(data["hooks"]):
            if not isinstance(raw, dict):
                continue
            rule = _compile_rule(path, idx, raw)
            if rule is None:
                continue
            if rule.name in seen_names:
                print(f'hook "{rule.name}": name conflict, skipped', file=sys.stderr)
                continue
            seen_names.add(rule.name)
            rules.append(rule)
        sources.append(path)

    return Engine(rules, sources)


def _compile_rule(source: str, idx: int, raw: dict) -> Rule | None:
    name = raw.get("name", "")
    if not name:
        print(f"hook [{idx}]: missing name, skipped", file=sys.stderr)
        return None

    event = parse_event(str(raw.get("event", "")))
    if event is None:
        print(f'hook "{name}": unknown event "{raw.get("event")}", skipped', file=sys.stderr)
        return None

    # action 解析
    action_raw = raw.get("action", {})
    if not isinstance(action_raw, dict):
        print(f'hook "{name}": invalid action, skipped', file=sys.stderr)
        return None
    action_type = action_raw.get("type", "")
    action = _compile_action(name, action_type, action_raw)
    if action is None:
        return None

    # 条件解析
    condition = _compile_condition(name, raw.get("if"))

    asyncio_mode = bool(raw.get("async", False))
    if asyncio_mode and is_blocking(event):
        print(f'hook "{name}": async not allowed for blocking events, skipped', file=sys.stderr)
        return None

    only_once = bool(raw.get("once", False))

    return Rule(
        name=name,
        event=event,
        action=action,
        condition=condition,
        asyncio_mode=asyncio_mode,
        only_once=only_once,
        source=source,
    )


def _compile_action(name: str, action_type: str, raw: dict) -> Action | None:
    if action_type == "shell":
        command = raw.get("command", "")
        if not command:
            print(f'hook "{name}": shell requires command, skipped', file=sys.stderr)
            return None
        try:
            timeout = _parse_duration(str(raw.get("timeout", "30s")))
        except ValueError:
            print(f'hook "{name}": invalid timeout, skipped', file=sys.stderr)
            return None
        return Action(type=ActionType.SHELL, shell=ShellAction(command=command, timeout=timeout))
    if action_type == "prompt":
        text = raw.get("text", "")
        if not text:
            print(f'hook "{name}": prompt requires text, skipped', file=sys.stderr)
            return None
        return Action(type=ActionType.PROMPT, prompt=PromptAction(text=text))
    if action_type == "http":
        url = raw.get("url", "")
        if not url:
            print(f'hook "{name}": http requires url, skipped', file=sys.stderr)
            return None
        return Action(
            type=ActionType.HTTP,
            http=HttpAction(
                url=url,
                method=raw.get("method", "POST"),
                body=raw.get("body"),
                headers=raw.get("headers", {}) or {},
            ),
        )
    if action_type == "subagent":
        agent_name = raw.get("agent_name", "")
        prompt = raw.get("prompt", "")
        if not agent_name or not prompt:
            print(
                f'hook "{name}": subagent requires agent_name and prompt, skipped', file=sys.stderr
            )
            return None
        return Action(
            type=ActionType.SUBAGENT,
            subagent=SubagentAction(agent_name=agent_name, prompt=prompt),
        )
    print(f'hook "{name}": unknown action type "{action_type}", skipped', file=sys.stderr)
    return None


def _compile_condition(name: str, raw: dict | None) -> Condition | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    all_of = raw.get("all_of")
    any_of = raw.get("any_of")
    if all_of and any_of:
        print(f'hook "{name}": all_of and any_of are mutually exclusive, skipped', file=sys.stderr)
        return None

    combine = CombineMode.ALL_OF
    atoms_raw = all_of
    if any_of:
        combine = CombineMode.ANY_OF
        atoms_raw = any_of

    if not isinstance(atoms_raw, list):
        return None

    atoms = []
    for atom in atoms_raw:
        if not isinstance(atom, dict):
            continue
        match = atom.get("match", {})
        if not isinstance(match, dict):
            continue
        field = match.get("field", "")
        match_type = match.get("type", "glob")
        pattern = ""
        if match_type == "not":
            pattern = "!" + str(match.get("inner", ""))
        elif match_type == "exact":
            pattern = "=" + str(match.get("value", ""))
        elif match_type == "regex":
            pattern = "~" + str(match.get("value", ""))
        else:  # glob
            pattern = str(match.get("value", ""))
        try:
            matcher = compile_matcher(pattern, is_command=False)
        except ValueError:
            continue
        atoms.append(AtomCondition(field=field, matcher=matcher))

    return Condition(combine=combine, atoms=atoms)
