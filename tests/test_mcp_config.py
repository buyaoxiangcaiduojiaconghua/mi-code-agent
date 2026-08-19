"""MCP 配置加载单测——两层合并/变量展开/字段校验/降级"""

from micodeagent.mcp.config import (
    _expand_vars,
    _merge_servers,
    _RawServer,
    _validate_server,
    load_config,
)


class TestMerge:
    def test_project_overrides_user(self):
        user = {"a": _RawServer(type="stdio", command="user-cmd")}
        project = {"a": _RawServer(type="http", url="project-url")}
        merged = _merge_servers(user, project)
        # 项目级完整覆盖：url 来自 project，command 被清空（整对象覆盖）
        assert merged["a"].url == "project-url"
        assert merged["a"].command == ""

    def test_keep_user_only(self):
        user = {"a": _RawServer(type="stdio", command="cmd")}
        project = {}
        merged = _merge_servers(user, project)
        assert merged["a"].command == "cmd"


class TestExpand:
    def test_expand_defined(self, monkeypatch):
        monkeypatch.setenv("FOO", "bar")
        s, undef = _expand_vars("hello ${FOO}")
        assert s == "hello bar"
        assert undef == []

    def test_expand_undefined(self):
        s, undef = _expand_vars("hello ${UNDEFINED_VAR_XYZ}")
        assert s == "hello "
        assert "UNDEFINED_VAR_XYZ" in undef

    def test_no_var(self):
        s, undef = _expand_vars("plain text")
        assert s == "plain text"
        assert undef == []


class TestValidate:
    def test_invalid_type(self):
        assert _validate_server("x", _RawServer(type="sse")) is None

    def test_missing_type(self):
        assert _validate_server("x", _RawServer(type="")) is None

    def test_stdio_missing_command(self):
        assert _validate_server("x", _RawServer(type="stdio")) is None

    def test_http_missing_url(self):
        assert _validate_server("x", _RawServer(type="http")) is None

    def test_valid_stdio(self):
        srv = _validate_server("x", _RawServer(type="stdio", command="ls"))
        assert srv is not None
        assert srv.command == "ls"

    def test_valid_http(self):
        srv = _validate_server("x", _RawServer(type="http", url="https://x"))
        assert srv is not None
        assert srv.url == "https://x"


class TestLoadConfig:
    def test_no_files(self, tmp_path):
        cfg = load_config(str(tmp_path))
        assert cfg.servers == {}

    def test_project_file(self, tmp_path):
        (tmp_path / ".micodeagent.yaml").write_text(
            "mcp_servers:\n  demo:\n    type: stdio\n    command: ls\n",
            encoding="utf-8",
        )
        cfg = load_config(str(tmp_path))
        assert "demo" in cfg.servers
        assert cfg.servers["demo"].command == "ls"

    def test_illegal_file(self, tmp_path, capsys):
        (tmp_path / ".micodeagent.yaml").write_text("mcp_servers: [unbalanced\n", encoding="utf-8")
        cfg = load_config(str(tmp_path))
        assert cfg.servers == {}
        assert "warn" in capsys.readouterr().err

    def test_command_not_expanded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CMD", "ls")
        (tmp_path / ".micodeagent.yaml").write_text(
            "mcp_servers:\n  demo:\n    type: stdio\n    command: '${CMD}'\n",
            encoding="utf-8",
        )
        cfg = load_config(str(tmp_path))
        # command 不做展开，保留字面量
        assert cfg.servers["demo"].command == "${CMD}"

    def test_skip_invalid_server(self, tmp_path, capsys):
        (tmp_path / ".micodeagent.yaml").write_text(
            "mcp_servers:\n"
            "  bad:\n    type: stdio\n"  # 缺 command，应跳过
            "  good:\n    type: stdio\n    command: ls\n",
            encoding="utf-8",
        )
        cfg = load_config(str(tmp_path))
        assert "bad" not in cfg.servers
        assert "good" in cfg.servers
        assert "warn" in capsys.readouterr().err
