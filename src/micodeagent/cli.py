"""MiCodeAgent CLI 入口

加载配置、构造工具注册中心、权限引擎与 MCP Manager，装配并启动 TUI。
"""

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

from micodeagent import __version__
from micodeagent import mcp as mcp_client
from micodeagent.config import ConfigError, effective_context_window, load
from micodeagent.permission import new_engine
from micodeagent.tool import new_default_registry


async def _amain() -> int:
    """异步入口：加载配置、装配工具与 MCP、启动 TUI。"""
    try:
        cfg = load(".micodeagent/config.yaml")
    except ConfigError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    registry = new_default_registry()
    root = str(Path.cwd().resolve())

    # 构造会话运行时（含上下文窗口）
    from micodeagent.agent.runtime import default_runtime

    runtime = default_runtime(root)
    runtime.context_window = effective_context_window(cfg.providers[0])

    # 加载项目指令 + 初始化记忆
    from micodeagent.instructions import Loader
    from micodeagent.memory import Manager as MemoryManager

    instruction_text = Loader(root).load()
    mem_mgr = MemoryManager(
        project_dir=str(Path(root) / ".micodeagent" / "memory"),
        user_dir=str(Path.home() / ".micodeagent" / "memory"),
        provider=None,
        model="",
    )
    memory_text = mem_mgr.load_index()

    # Skill 系统：加载 + 注册 LoadSkill 工具
    from micodeagent.skills import SkillLoader
    from micodeagent.tool.load_skill import LoadSkillTool

    skill_loader = SkillLoader(root)
    skill_loader.load_all()
    load_skill_tool = LoadSkillTool()
    registry.register(load_skill_tool)

    # Hook 系统
    from micodeagent import hook as hook_mod

    hook_engine = hook_mod.load(root)

    # 子 Agent 目录 + Agent 工具
    from micodeagent.agent.agent_tool import AgentTool
    from micodeagent.subagent import load_catalog

    subagent_catalog = load_catalog(root)
    agent_tool = AgentTool(subagent_catalog, parent=None)
    registry.register(agent_tool)

    # 会话写入器
    from micodeagent.session import Writer

    writer = Writer(runtime.session.session_dir)

    # 后台清理过期会话
    from micodeagent.session import clean_expired

    sessions_dir = str(Path(root) / ".micodeagent" / "sessions")
    asyncio.create_task(asyncio.to_thread(clean_expired, sessions_dir, timedelta(days=30)))

    # MCP 装配：加载配置 → 连接 server → 注册工具
    mcp_cfg = mcp_client.load_config(root)
    mcp_mgr = await mcp_client.new_manager(mcp_cfg, version=__version__)

    try:
        for t in mcp_mgr.tools():
            registry.register(t)

        engine, err = new_engine(root)
        if err is not None:
            print(f"⚠️ 权限引擎降级: {err}", file=sys.stderr)

        from micodeagent.tui.app import MiCodeAgentApp

        app = MiCodeAgentApp(
            cfg.providers,
            registry,
            engine,
            runtime,
            writer=writer,
            mem_mgr=mem_mgr,
            instruction_text=instruction_text,
            memory_text=memory_text,
            sessions_dir=sessions_dir,
            skill_loader=skill_loader,
            load_skill_tool=load_skill_tool,
            hook_engine=hook_engine,
        )
        await app.run_async()
    finally:
        await mcp_mgr.close()
        writer.close()
        if hook_engine is not None:
            await hook_engine.dispatch(
                hook_mod.Event.SESSION_END, {"session_id": runtime.session.session_id}
            )

    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
