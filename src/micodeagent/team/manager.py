"""团队管理器"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from micodeagent.team.persistence import (
    atomic_write_json,
    read_json,
    reload_from_disk_locked,
    sanitize,
)
from micodeagent.team.types import (
    MemberExistsError,
    MemberNotFoundError,
    Team,
    TeamHasActiveMembersError,
    TeammateInfo,
    TeamNotFoundError,
)


def _serialize_team(t: Team) -> dict:
    return {
        "name": t.name,
        "sanitized_name": t.sanitized_name,
        "lead_agent_id": t.lead_agent_id,
        "backend": t.backend,
        "description": t.description,
        "created_at": t.created_at,
        "members": [m.__dict__ for m in t.members],
    }


class Manager:
    """团队管理器。"""

    def __init__(self, home_dir: str, project_root: str, wt_mgr=None, task_mgr=None, reg=None):
        self.home_dir = home_dir
        self.project_root = project_root
        self.wt_mgr = wt_mgr
        self.task_mgr = task_mgr
        self.name_reg = reg
        self._teams_dir = str(Path(home_dir) / ".micodeagent" / "teams")
        self._teams: dict[str, Team] = {}
        Path(self._teams_dir).mkdir(parents=True, exist_ok=True)
        self._scan()

    def _scan(self) -> None:
        for sub in Path(self._teams_dir).iterdir():
            if not sub.is_dir():
                continue
            config = sub / "config.json"
            if not config.exists():
                continue
            try:
                data = read_json(config)
                team = Team(
                    name=data["name"],
                    sanitized_name=data.get("sanitized_name", ""),
                    lead_agent_id=data.get("lead_agent_id", ""),
                    backend=data.get("backend", "in_process"),
                    description=data.get("description", ""),
                    created_at=data.get("created_at", ""),
                    members=[TeammateInfo(**m) for m in data.get("members", [])],
                )
                team.config_dir = str(sub)
                team.config_path = str(config)
                team.tasks_path = str(sub / "tasks.json")
                team.mailbox_dir = str(sub / "mailbox")
                self._teams[team.name] = team
            except (KeyError, TypeError) as e:
                print(f"team: skip {sub}: {e}", file=sys.stderr)

    def get(self, name: str) -> Team | None:
        return self._teams.get(name)

    def list_(self) -> list[Team]:
        return sorted(self._teams.values(), key=lambda t: t.created_at)

    async def create(self, name: str, description: str) -> Team:
        sanitized = sanitize(name)
        final_name = name
        suffix = 2
        while final_name in self._teams:
            final_name = f"{name}-{suffix}"
            suffix += 1
        sanitized = sanitize(final_name)

        team = Team(
            name=final_name,
            sanitized_name=sanitized,
            description=description,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        config_dir = str(Path(self._teams_dir) / sanitized)
        team.config_dir = config_dir
        team.config_path = str(Path(config_dir) / "config.json")
        team.tasks_path = str(Path(config_dir) / "tasks.json")
        team.mailbox_dir = str(Path(config_dir) / "mailbox")
        Path(team.mailbox_dir).mkdir(parents=True, exist_ok=True)

        # 注册 Lead 成员
        lead = TeammateInfo(name="lead", agent_id=team.lead_agent_id or "lead")
        team.members.append(lead)
        atomic_write_json(team.config_path, _serialize_team(team))
        self._teams[team.name] = team
        return team

    async def delete(self, name: str, force: bool = False) -> None:
        team = self._teams.get(name)
        if team is None:
            raise TeamNotFoundError(name)
        if not force:
            for m in team.members:
                if m.is_active and m.name != "lead":
                    raise TeamHasActiveMembersError(name)
        shutil.rmtree(team.config_dir, ignore_errors=True)
        self._teams.pop(name, None)

    async def add_member(self, team_name: str, info: TeammateInfo) -> None:
        team = self._teams.get(team_name)
        if team is None:
            raise TeamNotFoundError(team_name)
        async with team._lock:
            await reload_from_disk_locked(team)
            if team.member_by_name(info.name) is not None:
                raise MemberExistsError(info.name)
            team.members.append(info)
            atomic_write_json(team.config_path, _serialize_team(team))

    async def set_member_active(self, team_name: str, name: str, active: bool) -> None:
        team = self._teams.get(team_name)
        if team is None:
            raise TeamNotFoundError(team_name)
        async with team._lock:
            await reload_from_disk_locked(team)
            member = team.member_by_name(name)
            if member is None:
                raise MemberNotFoundError(name)
            member.is_active = active
            atomic_write_json(team.config_path, _serialize_team(team))

    async def remove_member(self, team_name: str, name: str) -> None:
        team = self._teams.get(team_name)
        if team is None:
            raise TeamNotFoundError(team_name)
        async with team._lock:
            await reload_from_disk_locked(team)
            member = team.member_by_name(name)
            if member is None:
                raise MemberNotFoundError(name)
            team.members.remove(member)
            atomic_write_json(team.config_path, _serialize_team(team))
