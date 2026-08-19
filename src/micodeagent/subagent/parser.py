"""子 Agent 定义解析"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from micodeagent.subagent.definition import Definition, Source

AGENT_NAME_REGEX = re.compile(r"^[A-Za-z][A-Za-z0-9\-_]{0,31}$")
VALID_MODELS = {"", "inherit", "haiku", "sonnet", "opus"}


def parse_frontmatter_and_body(raw: str) -> tuple[dict, str]:
    """解析 YAML frontmatter。"""
    raw = raw.lstrip("﻿")  # 去 BOM
    if not raw.startswith("---"):
        raise ValueError("missing opening frontmatter")
    end = raw.find("\n---", 3)
    if end == -1:
        raise ValueError("unclosed frontmatter")
    meta = yaml.safe_load(raw[3:end].strip())
    body = raw[end + 4 :].lstrip("\n")
    if not isinstance(meta, dict):
        raise ValueError("frontmatter must be a mapping")
    return meta, body


def parse_definition(data: bytes, file_path: str, source: Source) -> Definition:
    """解析子 Agent 定义。"""
    raw = data.decode("utf-8")
    fm, body = parse_frontmatter_and_body(raw)

    name = str(fm.get("name", "")).strip()
    description = str(fm.get("description", "")).strip()
    if not name or not AGENT_NAME_REGEX.match(name):
        raise ValueError(f"invalid name: {name!r}")
    if not description:
        raise ValueError("missing description")

    model = str(fm.get("model") or "").strip()
    if model not in VALID_MODELS:
        print(f"subagent: invalid model {model!r}, fallback to inherit", file=sys.stderr)
        model = "inherit"

    permission_mode = str(fm.get("permissionMode") or "").strip()
    dont_ask = False
    if permission_mode == "dontAsk":
        dont_ask = True
        permission_mode = "default"

    return Definition(
        name=name,
        description=description,
        tools=[str(t) for t in (fm.get("tools") or [])],
        disallowed_tools=[str(t) for t in (fm.get("disallowedTools") or [])],
        model=model,
        max_turns=int(fm.get("maxTurns") or 0),
        permission_mode=permission_mode,
        dont_ask=dont_ask,
        background=bool(fm.get("background") or False),
        system_prompt=body,
        file_path=file_path,
        source=source,
    )


def parse_file(path: str, source: Source) -> Definition:
    return parse_definition(Path(path).read_bytes(), path, source)
