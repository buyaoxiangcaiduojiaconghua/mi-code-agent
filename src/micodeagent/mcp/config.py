"""MCP 配置加载与合并

从用户级 / 项目级两层 YAML 读取 mcp_servers，合并、展开 ${VAR}、校验。
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class ServerConfig:
    """单个 MCP server 的完整定义（已展开 ${VAR}、已校验）。"""

    type: Literal["stdio", "http"]
    command: str = ""  # stdio 必填
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""  # http 必填
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class Config:
    """mcp_servers 在内存中的归一化形式（已合并）。"""

    servers: dict[str, ServerConfig] = field(default_factory=dict)


@dataclass
class _RawServer:
    """未校验的原始 server 定义（含全部可能字段）。"""

    type: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)


def _load_file(path: Path) -> dict[str, _RawServer]:
    """读取单个配置文件，返回 server 映射；缺失/非法返回空 dict。"""
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        print(f"[mcp] warn: load {path} failed: {e}", file=sys.stderr)
        return {}

    if not isinstance(data, dict):
        return {}

    raw = data.get("mcp_servers") or {}
    if not isinstance(raw, dict):
        return {}

    servers: dict[str, _RawServer] = {}
    for name, item in raw.items():
        if not isinstance(item, dict):
            continue
        servers[str(name)] = _RawServer(
            type=str(item.get("type", "")),
            command=str(item.get("command", "")),
            args=[str(a) for a in (item.get("args") or [])],
            env={str(k): str(v) for k, v in (item.get("env") or {}).items()},
            url=str(item.get("url", "")),
            headers={str(k): str(v) for k, v in (item.get("headers") or {}).items()},
        )
    return servers


def _expand_vars(s: str) -> tuple[str, list[str]]:
    """展开 ${VAR}；返回 (展开后文本, 未定义变量名列表)。"""
    undefined: list[str] = []

    def repl(m: re.Match) -> str:
        var = m.group(1)
        if var in os.environ:
            return os.environ[var]
        undefined.append(var)
        return ""

    return _VAR_RE.sub(repl, s), undefined


def _apply_expansion(name: str, srv: _RawServer) -> None:
    """对 env / headers 的值展开 ${VAR}；未定义变量告警（同 server 同变量限一次）。"""
    warned: set[str] = set()

    def _expand_map(mapping: dict[str, str]) -> None:
        for k, v in list(mapping.items()):
            expanded, undefined = _expand_vars(v)
            mapping[k] = expanded
            for var in undefined:
                if var not in warned:
                    warned.add(var)
                    print(
                        f"[mcp] warn: undefined env var ${{{var}}} referenced by server {name}",
                        file=sys.stderr,
                    )

    _expand_map(srv.env)
    _expand_map(srv.headers)


def _merge_servers(
    user: dict[str, _RawServer], project: dict[str, _RawServer]
) -> dict[str, _RawServer]:
    """合并两层：项目级同名 server 完整覆盖用户级。"""
    merged = dict(user)
    merged.update(project)
    return merged


def _validate_server(name: str, srv: _RawServer) -> ServerConfig | None:
    """校验单个 server；非法返回 None + stderr 告警。"""
    if srv.type not in ("stdio", "http"):
        print(f"[mcp] warn: skip server {name}: invalid or missing type", file=sys.stderr)
        return None

    if srv.type == "stdio" and not srv.command:
        print(f"[mcp] warn: skip server {name}: stdio requires command", file=sys.stderr)
        return None

    if srv.type == "http" and not srv.url:
        print(f"[mcp] warn: skip server {name}: http requires url", file=sys.stderr)
        return None

    return ServerConfig(
        type=srv.type,
        command=srv.command,
        args=list(srv.args),
        env=dict(srv.env),
        url=srv.url,
        headers=dict(srv.headers),
    )


def load_config(root: str) -> Config:
    """加载并合并两层配置，永不抛出。"""
    # 用户级
    try:
        user_path = Path.home() / ".micodeagent" / "config.yaml"
        user_servers = _load_file(user_path)
    except (OSError, RuntimeError):
        user_servers = {}

    # 项目级
    project_path = Path(root) / ".micodeagent.yaml"
    project_servers = _load_file(project_path)

    # 变量展开
    for name, srv in user_servers.items():
        _apply_expansion(name, srv)
    for name, srv in project_servers.items():
        _apply_expansion(name, srv)

    # 合并 + 校验
    merged = _merge_servers(user_servers, project_servers)
    config = Config()
    for name, srv in merged.items():
        validated = _validate_server(name, srv)
        if validated is not None:
            config.servers[name] = validated

    return config
