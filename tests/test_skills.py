"""Skill 系统单测"""

from pathlib import Path

import pytest

from micodeagent.skills.loader import SkillLoader
from micodeagent.skills.parser import (
    SkillParseError,
    parse_frontmatter,
    parse_skill_file,
    substitute_arguments,
)
from micodeagent.tool.load_skill import LoadSkillTool

SKILL_MD = """---
name: test-skill
description: A test skill
mode: inline
---
Echo hello $ARGUMENTS
"""


class TestParser:
    def test_parse_valid(self):
        meta, body = parse_frontmatter(SKILL_MD)
        assert meta["name"] == "test-skill"
        assert "Echo hello" in body

    def test_missing_opening(self):
        with pytest.raises(SkillParseError, match="missing opening"):
            parse_frontmatter("no frontmatter")

    def test_unclosed(self):
        with pytest.raises(SkillParseError, match="unclosed"):
            parse_frontmatter("---\nname: x")

    def test_invalid_name(self, tmp_path):
        p = tmp_path / "s.md"
        p.write_text("---\nname: Bad Name\ndescription: d\n---\nbody")
        with pytest.raises(SkillParseError, match="invalid name"):
            parse_skill_file(str(p))

    def test_missing_name(self, tmp_path):
        p = tmp_path / "s.md"
        p.write_text("---\ndescription: d\n---\nbody")
        with pytest.raises(SkillParseError, match="missing name"):
            parse_skill_file(str(p))

    def test_invalid_mode(self, tmp_path):
        p = tmp_path / "s.md"
        p.write_text("---\nname: x\ndescription: d\nmode: bad\n---\nbody")
        with pytest.raises(SkillParseError, match="invalid mode"):
            parse_skill_file(str(p))

    def test_fork_with_context(self, tmp_path):
        p = tmp_path / "s.md"
        p.write_text("---\nname: fork-skill\ndescription: d\nmode: fork\ncontext: full\n---\nbody")
        skill = parse_skill_file(str(p))
        assert skill.mode == "fork"
        assert skill.context == "full"


class TestSubstitute:
    def test_with_args(self):
        assert substitute_arguments("hello $ARGUMENTS", "world") == "hello world"

    def test_no_placeholder(self):
        assert substitute_arguments("hello", "world") == "hello"

    def test_multiple(self):
        assert substitute_arguments("$ARGUMENTS $ARGUMENTS", "x") == "x x"


class TestLoader:
    def _write_skill(self, root: Path, name: str, desc: str = "d", subdir: bool = False):
        root.mkdir(parents=True, exist_ok=True)
        if subdir:
            d = root / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: {desc}\nmode: inline\n---\nbody of {name}"
            )
        else:
            (root / f"{name}.md").write_text(
                f"---\nname: {name}\ndescription: {desc}\nmode: inline\n---\nbody of {name}"
            )

    def test_load_project(self, tmp_path):
        self._write_skill(tmp_path / ".micodeagent" / "skills", "alpha")
        loader = SkillLoader(str(tmp_path))
        loader.load_all()
        assert loader.get("alpha") is not None

    def test_catalog(self, tmp_path):
        self._write_skill(tmp_path / ".micodeagent" / "skills", "alpha")
        self._write_skill(tmp_path / ".micodeagent" / "skills", "beta")
        loader = SkillLoader(str(tmp_path))
        loader.load_all()
        names = [n for n, _ in loader.get_catalog()]
        assert names == ["alpha", "beta"]

    def test_get_unknown(self, tmp_path):
        loader = SkillLoader(str(tmp_path))
        loader.load_all()
        assert loader.get("unknown") is None

    def test_directory_skill(self, tmp_path):
        self._write_skill(tmp_path / ".micodeagent" / "skills", "dir-skill", subdir=True)
        loader = SkillLoader(str(tmp_path))
        loader.load_all()
        skill = loader.get("dir-skill")
        assert skill is not None
        assert skill.is_directory

    def test_skip_bad_file(self, tmp_path, capsys):
        root = tmp_path / ".micodeagent" / "skills"
        root.mkdir(parents=True)
        (root / "bad.md").write_text("not a skill")
        loader = SkillLoader(str(tmp_path))
        loader.load_all()
        assert loader.get("bad") is None


class TestLoadSkillTool:
    def test_category_read(self):
        tool = LoadSkillTool()
        assert tool.read_only is True
        assert tool.name() == "load_skill"

    @pytest.mark.asyncio
    async def test_not_initialized(self):
        tool = LoadSkillTool()
        r = await tool.execute('{"name": "x"}')
        assert r.is_error
        assert "初始化" in r.content

    @pytest.mark.asyncio
    async def test_load_unknown(self, tmp_path):
        loader = SkillLoader(str(tmp_path))
        loader.load_all()

        class FakeAgent:
            def __init__(self):
                self.skills = {}

            def activate_skill(self, name, body):
                self.skills[name] = body

        agent = FakeAgent()
        tool = LoadSkillTool()
        tool.set_loader(loader)
        tool.set_agent(agent)
        r = await tool.execute('{"name": "unknown"}')
        assert r.is_error

    @pytest.mark.asyncio
    async def test_load_existing(self, tmp_path):
        (tmp_path / ".micodeagent" / "skills").mkdir(parents=True)
        (tmp_path / ".micodeagent" / "skills" / "demo.md").write_text(
            "---\nname: demo\ndescription: d\nmode: inline\n---\nEcho demo"
        )
        loader = SkillLoader(str(tmp_path))
        loader.load_all()

        class FakeAgent:
            def __init__(self):
                self.skills = {}

            def activate_skill(self, name, body):
                self.skills[name] = body

        agent = FakeAgent()
        tool = LoadSkillTool()
        tool.set_loader(loader)
        tool.set_agent(agent)
        r = await tool.execute('{"name": "demo"}')
        assert not r.is_error
        assert "demo" in agent.skills
