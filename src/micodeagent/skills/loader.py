"""Skill 加载器：两级搜索 + 热重载"""

from __future__ import annotations

import logging
from pathlib import Path

from micodeagent.skills.parser import SkillDef, SkillParseError, parse_skill_file

logger = logging.getLogger(__name__)

PROJECT_SKILLS_DIR = ".micodeagent/skills"
USER_SKILLS_DIR = "~/.micodeagent/skills"


class SkillLoader:
    """加载项目级与用户级 skill，支持热重载。"""

    def __init__(self, work_dir: str):
        self._project_dir = str(Path(work_dir) / PROJECT_SKILLS_DIR)
        self._user_dir = str(Path(USER_SKILLS_DIR).expanduser())
        self._skills: dict[str, SkillDef] = {}
        self._cache: dict[str, SkillDef] = {}

    def load_all(self) -> None:
        """按 project → user 顺序扫描，首次出现的 name 保留。"""
        self._skills = {}
        self._scan_directory(self._project_dir, "project")
        self._scan_directory(self._user_dir, "user")
        self._cache = dict(self._skills)

    def reload(self) -> None:
        """重新加载。"""
        self.load_all()

    def _scan_directory(self, path: str, source: str) -> None:
        base = Path(path)
        if not base.is_dir():
            return
        # 顶层 *.md（非 SKILL.md）是单文件 skill
        for f in sorted(base.glob("*.md")):
            if f.name == "SKILL.md":
                continue
            self._try_load(str(f), source, is_directory=False)
        # 子目录下的 SKILL.md 是目录型 skill
        for skill_dir in sorted(base.iterdir()):
            if skill_dir.is_dir():
                entry = skill_dir / "SKILL.md"
                if entry.exists():
                    self._try_load(str(entry), source, is_directory=True)

    def _try_load(self, path: str, source: str, is_directory: bool) -> None:
        try:
            skill = parse_skill_file(path)
        except SkillParseError as e:
            logger.warning("Skipping %s skill '%s': %s", source, path, e)
            return
        except OSError as e:
            logger.warning("Skipping %s skill '%s': %s", source, path, e)
            return
        skill.is_directory = is_directory
        if skill.name not in self._skills:
            self._skills[skill.name] = skill

    def get(self, name: str) -> SkillDef | None:
        """按名查找，命中后强制重读（热重载），失败回退旧版本。"""
        if name not in self._skills:
            return None
        cached = self._cache.get(name)
        source_path = self._skills[name].source_path
        try:
            skill = parse_skill_file(source_path)
            self._cache[name] = skill
            return skill
        except (SkillParseError, OSError) as e:
            logger.warning("热重载失败，回退旧版本: %s", e)
            return cached or self._skills[name]

    def get_catalog(self) -> list[tuple[str, str]]:
        """返回 [(name, description), ...] 列表。"""
        return [(s.name, s.description) for s in self._skills.values()]

    def get_source_label(self, name: str) -> str:
        """按路径前缀返回 project | user。"""
        skill = self._skills.get(name)
        if skill is None:
            return "unknown"
        if skill.source_path.startswith(self._project_dir):
            return "project"
        return "user"
