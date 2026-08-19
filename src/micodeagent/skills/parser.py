"""Skill 定义解析"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

_NAME_RE = re.compile(r"^[a-z][a-z0-9\-]*$")
_VALID_MODES = {"inline", "fork"}
_VALID_CONTEXTS = {"full", "recent", "none"}


class SkillParseError(Exception):
    """Skill 解析错误"""


@dataclass
class SkillDef:
    """单个 Skill 的定义。"""

    name: str
    description: str
    prompt_body: str
    mode: str = "inline"  # inline / fork
    model: str = ""  # 可选指定模型
    context: str = "none"  # full / recent / none（fork 模式）
    tools: list[str] = field(default_factory=list)  # 工具白名单
    source_path: str = ""
    is_directory: bool = False


def parse_frontmatter(raw: str) -> tuple[dict, str]:
    """解析 YAML frontmatter，返回 (meta, body)。"""
    if not raw.startswith("---"):
        raise SkillParseError("missing opening frontmatter")
    end = raw.find("\n---", 3)
    if end == -1:
        raise SkillParseError("unclosed frontmatter")
    meta_text = raw[3:end].strip()
    body = raw[end + 4 :].strip()
    try:
        meta = yaml.safe_load(meta_text)
    except yaml.YAMLError as e:
        raise SkillParseError(f"invalid yaml: {e}")
    if not isinstance(meta, dict):
        raise SkillParseError("frontmatter must be a mapping")
    return meta, body


def _validate_meta(meta: dict) -> None:
    if "name" not in meta or not meta["name"]:
        raise SkillParseError("missing name")
    if not _NAME_RE.match(str(meta["name"])):
        raise SkillParseError("invalid name format")
    if "description" not in meta or not meta["description"]:
        raise SkillParseError("missing description")
    mode = meta.get("mode", "inline")
    if mode not in _VALID_MODES:
        raise SkillParseError(f"invalid mode: {mode}")
    context = meta.get("context", "none")
    if context not in _VALID_CONTEXTS:
        raise SkillParseError(f"invalid context: {context}")


def parse_skill_file(path: str) -> SkillDef:
    """解析单个 skill 文件。"""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    meta, body = parse_frontmatter(raw)
    _validate_meta(meta)
    return SkillDef(
        name=str(meta["name"]),
        description=str(meta["description"]),
        prompt_body=body,
        mode=meta.get("mode", "inline"),
        model=str(meta.get("model", "")),
        context=meta.get("context", "none"),
        tools=[str(t) for t in (meta.get("tools") or [])],
        source_path=path,
        is_directory=path.endswith("SKILL.md"),
    )


def substitute_arguments(prompt_body: str, args: str) -> str:
    """把正文中的 $ARGUMENTS 占位符替换为用户传入的内容。"""
    return prompt_body.replace("$ARGUMENTS", args)
