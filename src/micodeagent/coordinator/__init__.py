"""Coordinator 模式"""

from __future__ import annotations

import os


def env_truthy(v: str) -> bool:
    return v.lower() in {"1", "true", "yes"}


def is_enabled(cfg) -> bool:
    """双锁：配置 features.coordinator_mode + 环境变量 MEWCODE_COORDINATOR_MODE。"""
    config_enabled = bool(getattr(getattr(cfg, "features", None), "coordinator_mode", False))
    env_enabled = env_truthy(os.environ.get("MEWCODE_COORDINATOR_MODE", ""))
    return config_enabled and env_enabled


def allowed_tools() -> list[str]:
    """Coordinator 模式允许的工具。"""
    return [
        "Agent",
        "TaskCreate",
        "TaskGet",
        "TaskList",
        "TaskUpdate",
        "SendMessage",
        "TeamCreate",
        "TeamDelete",
        "read_file",
        "glob",
        "grep",
        "bash",
    ]


def system_prompt_suffix() -> str:
    """Coordinator 模式系统提示后缀。"""
    return (
        "你处于 Coordinator 模式。"
        "你的职责是拆解目标、派生队员、分配任务、收发消息、合并代码。"
        "派完队员后必须停手等待汇报，禁止立刻自己 read_file/glob/grep/bash 探索。"
        "只在 Research 首次定位、Synthesis 读队员产出、Verification 收敛时，"
        "才允许自己使用读类工具。"
    )
