"""工具系统单测——注册中心 + 6 个核心工具"""

import pytest

from micodeagent.tool import Registry, new_default_registry


class TestRegistry:
    def test_definitions_count(self):
        r = new_default_registry()
        defs = r.definitions()
        assert len(defs) == 6
        names = [d.name for d in defs]
        assert names == ["read_file", "write_file", "edit_file", "bash", "glob", "grep"]

    def test_get_hit(self):
        r = new_default_registry()
        t = r.get("read_file")
        assert t is not None
        assert t.name() == "read_file"

    def test_get_miss(self):
        r = new_default_registry()
        assert r.get("nonexistent") is None

    def test_duplicate_register(self):
        from micodeagent.tool.read_file import ReadFileTool

        r = Registry()
        r.register(ReadFileTool())
        with pytest.raises(ValueError, match="已注册"):
            r.register(ReadFileTool())

    @pytest.mark.asyncio
    async def test_execute_unknown(self):
        r = new_default_registry()
        result = await r.execute("nonexistent", "{}")
        assert result.is_error
        assert "未知工具" in result.content

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """注入极短超时跑 sleep 5，验证超时返回 is_error。"""
        r = new_default_registry()
        result = await r.execute("bash", '{"command": "sleep 5"}', timeout=0.5)
        assert result.is_error
        assert "超时" in result.content


class TestReadFile:
    @pytest.fixture
    def reg(self):
        return new_default_registry()

    @pytest.mark.asyncio
    async def test_read_existing(self, reg, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3")
        result = await reg.execute("read_file", f'{{"path": "{f}"}}')
        assert not result.is_error
        assert "1\tline1" in result.content
        assert "2\tline2" in result.content
        assert "3\tline3" in result.content

    @pytest.mark.asyncio
    async def test_read_not_exist(self, reg):
        result = await reg.execute("read_file", '{"path": "/nonexistent/file.txt"}')
        assert result.is_error
        assert "不存在" in result.content

    @pytest.mark.asyncio
    async def test_read_dir(self, reg, tmp_path):
        result = await reg.execute("read_file", f'{{"path": "{tmp_path}"}}')
        assert result.is_error


class TestWriteFile:
    @pytest.fixture
    def reg(self):
        return new_default_registry()

    @pytest.mark.asyncio
    async def test_write_and_read_back(self, reg, tmp_path):
        f = tmp_path / "out.txt"
        result = await reg.execute("write_file", f'{{"path": "{f}", "content": "hello"}}')
        assert not result.is_error
        assert str(f) in result.content
        assert f.read_text() == "hello"

    @pytest.mark.asyncio
    async def test_write_nested(self, reg, tmp_path):
        f = tmp_path / "a" / "b" / "c.txt"
        result = await reg.execute("write_file", f'{{"path": "{f}", "content": "nested"}}')
        assert not result.is_error
        assert f.read_text() == "nested"


class TestEditFile:
    @pytest.fixture
    def reg(self):
        return new_default_registry()

    @pytest.mark.asyncio
    async def test_unique_match(self, reg, tmp_path):
        f = tmp_path / "e.txt"
        f.write_text("hello world")
        result = await reg.execute(
            "edit_file",
            f'{{"path": "{f}", "old_string": "hello", "new_string": "hi"}}',
        )
        assert not result.is_error
        assert f.read_text() == "hi world"

    @pytest.mark.asyncio
    async def test_no_match(self, reg, tmp_path):
        f = tmp_path / "e.txt"
        f.write_text("hello")
        result = await reg.execute(
            "edit_file",
            f'{{"path": "{f}", "old_string": "xyz", "new_string": "abc"}}',
        )
        assert result.is_error
        assert "未找到匹配" in result.content

    @pytest.mark.asyncio
    async def test_multiple_match(self, reg, tmp_path):
        f = tmp_path / "e.txt"
        f.write_text("ab ab")
        result = await reg.execute(
            "edit_file",
            f'{{"path": "{f}", "old_string": "ab", "new_string": "cd"}}',
        )
        assert result.is_error
        assert "不唯一" in result.content


class TestBash:
    @pytest.fixture
    def reg(self):
        return new_default_registry()

    @pytest.mark.asyncio
    async def test_echo(self, reg):
        result = await reg.execute("bash", '{"command": "echo hello"}')
        assert not result.is_error
        assert "hello" in result.content
        assert "exit_code: 0" in result.content

    @pytest.mark.asyncio
    async def test_error_command(self, reg):
        result = await reg.execute("bash", '{"command": "nonexistent_cmd_12345"}')
        # 非零退出不设 is_error，模型自己判断
        assert result.content


class TestGlob:
    @pytest.fixture
    def reg(self):
        return new_default_registry()

    @pytest.mark.asyncio
    async def test_glob_py(self, reg):
        result = await reg.execute("glob", '{"pattern": "**/*.py", "path": "src/micodeagent"}')
        assert not result.is_error
        assert "src/micodeagent" in result.content

    @pytest.mark.asyncio
    async def test_glob_no_match(self, reg):
        result = await reg.execute("glob", '{"pattern": "*.xyz", "path": "."}')
        assert not result.is_error
        assert "无匹配" in result.content


class TestGrep:
    @pytest.fixture
    def reg(self):
        return new_default_registry()

    @pytest.mark.asyncio
    async def test_grep_keyword(self, reg):
        result = await reg.execute(
            "grep",
            '{"pattern": "class ReadFileTool", "path": "src/micodeagent/tool", "glob": "*.py"}',
        )
        assert not result.is_error
        assert "read_file.py" in result.content

    @pytest.mark.asyncio
    async def test_grep_no_hit(self, reg):
        result = await reg.execute(
            "grep", '{"pattern": "zzzNOTFOUNDzzz", "path": "src/micodeagent"}'
        )
        assert not result.is_error
        assert "无命中" in result.content

    @pytest.mark.asyncio
    async def test_grep_bad_regex(self, reg):
        result = await reg.execute("grep", '{"pattern": "[[["}')
        assert result.is_error
        assert "正则非法" in result.content
