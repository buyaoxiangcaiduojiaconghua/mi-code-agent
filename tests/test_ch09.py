"""ch09 新包核心单测——instructions / session / memory"""

import os
import tempfile
from datetime import timedelta

from micodeagent.compact.state import new_session_context, parse_session_time
from micodeagent.instructions import Loader
from micodeagent.memory.store import Store
from micodeagent.memory.types import UpdateAction
from micodeagent.session.cleanup import clean_expired
from micodeagent.session.load import load_session
from micodeagent.session.writer import Writer


class TestSessionId:
    def test_new_format(self):
        ctx = new_session_context(".")
        assert "-" in ctx.session_id
        ts = parse_session_time(ctx.session_id)
        assert ts is not None
        assert os.path.isdir(ctx.spill_dir)

    def test_parse_old_format(self):
        assert parse_session_time("bad-id") is None


class TestInstructions:
    def test_load_empty(self):
        with tempfile.TemporaryDirectory() as d:
            loader = Loader(d)
            result = loader.load()
            assert result == ""

    def test_load_single(self, tmp_path):
        (tmp_path / "MEWCODE.md").write_text("hello")
        loader = Loader(str(tmp_path))
        assert "hello" in loader.load()

    def test_include(self, tmp_path):
        (tmp_path / "MEWCODE.md").write_text("main\n@include sub.md")
        (tmp_path / "sub.md").write_text("sub")
        loader = Loader(str(tmp_path))
        result = loader.load()
        assert "main" in result
        assert "sub" in result

    def test_include_depth_limit(self, tmp_path):
        # 构造 6 层嵌套
        (tmp_path / "MEWCODE.md").write_text("@include a.md")
        (tmp_path / "a.md").write_text("@include b.md")
        (tmp_path / "b.md").write_text("@include c.md")
        (tmp_path / "c.md").write_text("@include d.md")
        (tmp_path / "d.md").write_text("@include e.md")
        (tmp_path / "e.md").write_text("final")
        loader = Loader(str(tmp_path), max_depth=3)
        result = loader.load()
        assert "超过最大嵌套深度" in result


class TestSessionWriter:
    def test_write_and_read(self, tmp_path):
        from micodeagent.llm import Message

        d = str(tmp_path / "session")
        with Writer(d) as w:
            w.append(Message(role="user", content="hi"), model="test", is_first=True)
            w.append(Message(role="assistant", content="hello"))

        msgs = load_session(d)
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[0].content == "hi"

    def test_compact_marker(self, tmp_path):
        from micodeagent.llm import Message

        d = str(tmp_path / "session")
        with Writer(d) as w:
            w.append(Message(role="user", content="old"))
            w.write_compact_marker()
            w.append(Message(role="user", content="new"))

        msgs = load_session(d)
        # compact 后只加载新消息
        assert len(msgs) == 1
        assert msgs[0].content == "new"


class TestMemoryStore:
    def test_create_note(self, tmp_path):
        store = Store(str(tmp_path / "memory"))
        store.apply(
            [
                UpdateAction(
                    action="create",
                    level="project",
                    type="project_knowledge",
                    title="test",
                    slug="test",
                    content="note content",
                )
            ]
        )
        index = store.load_index()
        assert "test" in index
        assert "note content" in index
        assert os.path.exists(str(tmp_path / "memory" / "project_knowledge_test.md"))


class TestCleanup:
    def test_clean_expired(self, tmp_path):

        sessions_dir = str(tmp_path / "sessions")
        # 创建旧格式目录（不应被删除）
        old_dir = os.path.join(sessions_dir, "1717000000-abc12345")
        os.makedirs(old_dir)
        # 创建过期的新格式目录
        expired_dir = os.path.join(sessions_dir, "20200101-000000-a1b2")
        os.makedirs(expired_dir)
        # 创建活跃的新格式目录
        active_dir = os.path.join(sessions_dir, "20260801-000000-c3d4")
        os.makedirs(active_dir)

        clean_expired(sessions_dir, timedelta(days=30))

        assert os.path.exists(old_dir)  # 旧格式跳过
        assert not os.path.exists(expired_dir)  # 过期删除
        assert os.path.exists(active_dir)  # 活跃保留
