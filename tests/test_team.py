"""ch15 团队协作单测"""

import asyncio

import pytest

from micodeagent.coordinator import allowed_tools, is_enabled, system_prompt_suffix
from micodeagent.team.mailbox import Box, Message
from micodeagent.team.manager import Manager
from micodeagent.team.persistence import sanitize
from micodeagent.team.registry import AgentNameRegistry
from micodeagent.team.tasks import Filter, Patch, Store, Task
from micodeagent.team.types import TeammateInfo


class TestSanitize:
    def test_sanitize(self):
        assert sanitize("foo bar/baz") == "foo-bar-baz"
        assert sanitize("foo..bar") == "foo..bar"
        assert sanitize("") == ""


class TestRegistry:
    def test_register_resolve(self):
        r = AgentNameRegistry()
        r.register("alice", "agent-1")
        assert r.resolve("alice") == "agent-1"
        assert r.resolve("agent-1") == "agent-1"
        assert r.name_of("agent-1") == "alice"

    def test_register_override(self):
        r = AgentNameRegistry()
        r.register("alice", "agent-1")
        r.register("alice", "agent-2")
        assert r.resolve("alice") == "agent-2"
        assert r.name_of("agent-1") is None

    def test_unregister(self):
        r = AgentNameRegistry()
        r.register("alice", "agent-1")
        r.unregister("alice")
        assert r.resolve("alice") is None


class TestMailbox:
    @pytest.mark.asyncio
    async def test_write_read(self, tmp_path):
        box = Box(str(tmp_path))
        await box.write("agent-1", Message(from_="lead", text="hello"))
        msgs = await box.read("agent-1")
        assert len(msgs) == 1
        assert msgs[0].text == "hello"
        assert msgs[0].from_ == "lead"

    @pytest.mark.asyncio
    async def test_read_unread_mark_read(self, tmp_path):
        box = Box(str(tmp_path))
        await box.write("a", Message(from_="x", text="m1"))
        await box.write("a", Message(from_="x", text="m2"))
        indices, unread = await box.read_unread("a")
        assert len(unread) == 2
        await box.mark_read("a", indices)
        _, unread2 = await box.read_unread("a")
        assert len(unread2) == 0

    @pytest.mark.asyncio
    async def test_concurrent_write(self, tmp_path):
        box = Box(str(tmp_path))

        async def write_one(i):
            await box.write("a", Message(from_="x", text=f"m{i}"))

        await asyncio.gather(*[write_one(i) for i in range(10)])
        msgs = await box.read("a")
        assert len(msgs) == 10


class TestTasks:
    @pytest.mark.asyncio
    async def test_create_get(self, tmp_path):
        store = Store(str(tmp_path / "tasks.json"))
        tid = await store.create(Task(title="t1"))
        t = await store.get(tid)
        assert t.title == "t1"

    @pytest.mark.asyncio
    async def test_blocked_by_bidirectional(self, tmp_path):
        store = Store(str(tmp_path / "tasks.json"))
        a = await store.create(Task(title="a"))
        b = await store.create(Task(title="b"))
        await store.update(b, Patch(add_blocked_by=[a]))
        ta = await store.get(a)
        assert b in ta.blocks

    @pytest.mark.asyncio
    async def test_list_filter(self, tmp_path):
        store = Store(str(tmp_path / "tasks.json"))
        await store.create(Task(title="t1", status="todo"))
        await store.create(Task(title="t2", status="done"))
        todo = await store.list_(Filter(status="todo"))
        assert len(todo) == 1


class TestManager:
    @pytest.mark.asyncio
    async def test_create_get_delete(self, tmp_path):
        mgr = Manager(str(tmp_path), str(tmp_path))
        team = await mgr.create("demo", "test team")
        assert mgr.get("demo") is not None
        assert team.sanitized_name == "demo"
        await mgr.delete("demo", force=True)
        assert mgr.get("demo") is None

    @pytest.mark.asyncio
    async def test_add_set_active(self, tmp_path):
        mgr = Manager(str(tmp_path), str(tmp_path))
        team = await mgr.create("demo", "")
        await mgr.add_member("demo", TeammateInfo(name="alice", agent_id="agent-1"))
        assert team.member_by_name("alice") is not None
        await mgr.set_member_active("demo", "alice", True)
        assert team.member_by_name("alice").is_active

    @pytest.mark.asyncio
    async def test_add_duplicate_member(self, tmp_path):
        mgr = Manager(str(tmp_path), str(tmp_path))
        await mgr.create("demo", "")
        await mgr.add_member("demo", TeammateInfo(name="alice"))
        with pytest.raises(Exception):
            await mgr.add_member("demo", TeammateInfo(name="alice"))


class TestCoordinator:
    def test_allowed_tools(self):
        tools = allowed_tools()
        assert "Agent" in tools
        assert "SendMessage" in tools
        assert "read_file" in tools

    def test_is_enabled_requires_both(self):
        class Cfg:
            class Features:
                coordinator_mode = False

            features = Features()

        assert not is_enabled(Cfg())

    def test_system_prompt_suffix(self):
        assert "Coordinator" in system_prompt_suffix()
