"""prompt 模块单测——装配/确定性/双重强化/环境"""

import os

from micodeagent.prompt import (
    Environment,
    Module,
    assemble_system,
    build_system_prompt,
    gather_environment,
    plan_reminder,
    system_reminder,
)


class TestAssemble:
    def test_order_by_priority(self):
        """模块按 priority 升序排列。"""
        mods = [
            Module(name="B", priority=20, content="B"),
            Module(name="A", priority=10, content="A"),
        ]
        result = assemble_system(mods)
        assert result == "A\n\nB"

    def test_skip_empty(self):
        """空 content 模块跳过，不留多余空行。"""
        mods = [
            Module(name="A", priority=10, content="A"),
            Module(name="B", priority=20, content=""),
            Module(name="C", priority=30, content="C"),
        ]
        result = assemble_system(mods)
        assert result == "A\n\nC"
        assert "\n\n\n" not in result

    def test_build_system_prompt_not_empty(self):
        """build_system_prompt 返回非空文本。"""
        result = build_system_prompt()
        assert len(result) > 100

    def test_determinism(self):
        """两次调用逐字节相等（N1）。"""
        assert build_system_prompt() == build_system_prompt()

    def test_identity_before_tool_usage(self):
        """身份模块(10)在工具使用模块(50)之前。"""
        result = build_system_prompt()
        idx_identity = result.find("MiCodeAgent")
        idx_tool = result.find("Tool Selection Rules")
        assert idx_identity < idx_tool

    def test_sections_separated(self):
        """模块间以空行分隔。"""
        result = build_system_prompt()
        assert "\n\n" in result

    def test_dual_reinforcement_edit(self):
        """系统提示含「编辑前必先读」的双重强化。"""
        result = build_system_prompt()
        assert "编辑" in result or "edit_file" in result.lower()
        assert "read_file" in result

    def test_dual_reinforcement_dedicated_tool(self):
        """系统提示含「优先用专用工具」的双重强化。"""
        result = build_system_prompt()
        assert "NEVER use bash" in result or "不要用 bash" in result


class TestReminder:
    def test_system_reminder_wrapping(self):
        wrapped = system_reminder("test")
        assert "<system-reminder>" in wrapped
        assert "</system-reminder>" in wrapped
        assert "test" in wrapped

    def test_plan_reminder_full(self):
        result = plan_reminder(True)
        assert "<system-reminder>" in result
        assert "plan" in result.lower() or "PLAN" in result

    def test_plan_reminder_concise(self):
        result = plan_reminder(False)
        assert "<system-reminder>" in result
        # 精简版比完整版短
        assert len(result) < len(plan_reminder(True))


class TestEnvironment:
    def test_render(self):
        env = Environment(
            working_dir="/tmp",
            platform="darwin",
            date="2026-01-01",
            git_status="M a.txt",
            version="dev",
            model="gpt",
        )
        rendered = env.render()
        assert "/tmp" in rendered
        assert "darwin" in rendered
        assert "2026-01-01" in rendered
        assert "M a.txt" in rendered
        assert "dev" in rendered
        assert "gpt" in rendered

    def test_render_empty_git(self):
        env = Environment(
            working_dir="/tmp",
            platform="linux",
            date="2026-01-01",
            git_status="",
            version="dev",
            model="gpt",
        )
        rendered = env.render()
        assert "Git" not in rendered

    def test_gather_environment(self):
        env = gather_environment("dev", "test-model")
        assert env.working_dir == os.getcwd()
        assert env.platform
        assert env.date
        assert env.version == "dev"
        assert env.model == "test-model"
        # git_status 可为空（非 git 目录），但不抛异常
