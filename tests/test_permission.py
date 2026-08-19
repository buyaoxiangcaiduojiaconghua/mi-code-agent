"""权限系统单测——黑名单、沙箱、规则、配置、引擎"""

from micodeagent.llm import ToolCall
from micodeagent.permission import Category, Decision, Mode, next_mode, parse_mode
from micodeagent.permission.blacklist import hits_blacklist
from micodeagent.permission.engine import mode_fallback, new_engine
from micodeagent.permission.rule import Rule, RuleSet, match_pattern, parse_rule
from micodeagent.permission.sandbox import sandbox_ok
from micodeagent.permission.settings import (
    categorize,
    extract_target,
    friendly_name,
)


class TestBlacklist:
    def test_hits_dangerous(self):
        assert hits_blacklist("rm -rf /")
        assert hits_blacklist("rm -fr ~")
        assert hits_blacklist("rm -rf /tmp/*")
        assert hits_blacklist("dd if=/dev/zero of=/dev/sda")

    def test_no_false_positive(self):
        assert not hits_blacklist("rm -rf ./build")
        assert not hits_blacklist("git status")
        assert not hits_blacklist("ls -la")

    def test_fork_bomb(self):
        assert hits_blacklist(":(){ :|:& };:")


class TestSandbox:
    def test_inside_root(self, tmp_path):
        root = str(tmp_path)
        (tmp_path / "a.txt").write_text("hi")
        assert sandbox_ok(root, "a.txt")
        assert sandbox_ok(root, str(tmp_path / "a.txt"))

    def test_outside_root(self, tmp_path):
        root = str(tmp_path)
        assert not sandbox_ok(root, "/etc/passwd")
        assert not sandbox_ok(root, "../outside")

    def test_new_file_ancestor_fallback(self, tmp_path):
        root = str(tmp_path)
        new_file = str(tmp_path / "a" / "b" / "c.txt")
        assert sandbox_ok(root, new_file)

    def test_symlink_escape(self, tmp_path):
        root = str(tmp_path)
        link = tmp_path / "external"
        link.symlink_to("/etc")
        assert not sandbox_ok(root, str(link))

    def test_empty_path(self, tmp_path):
        assert sandbox_ok(str(tmp_path), "")


class TestRules:
    def test_parse_simple(self):
        r, ok = parse_rule("Bash(git *)")
        assert ok
        assert r.tool == "Bash"
        assert r.pattern == "git *"

    def test_parse_no_pattern(self):
        r, ok = parse_rule("Read")
        assert ok
        assert r.tool == "Read"
        assert r.pattern == ""

    def test_parse_invalid(self):
        _, ok = parse_rule("")
        assert not ok
        _, ok = parse_rule("Bash(git *")
        assert not ok

    def test_match_pattern_exact(self):
        assert match_pattern("git status", "git status")
        assert not match_pattern("git status", "git push")

    def test_match_pattern_glob(self):
        assert match_pattern("git *", "git push")
        assert match_pattern("git *", "git status")
        assert not match_pattern("git *", "npm install")

    def test_ruleset_deny_priority(self):
        rs = RuleSet(
            deny=[Rule("Bash", "rm *", False)],
            allow=[Rule("Bash", "*", True)],
        )
        dec, hit = rs.match("Bash", "rm -rf")
        assert hit
        assert dec == Decision.DENY


class TestSettings:
    def test_friendly_name(self):
        assert friendly_name("bash") == "Bash"
        assert friendly_name("read_file") == "Read"
        assert friendly_name("write_file") == "Write"
        assert friendly_name("unknown") == "unknown"

    def test_categorize(self):
        assert categorize("read_file", True) == Category.READ
        assert categorize("write_file", False) == Category.WRITE
        assert categorize("bash", False) == Category.EXEC
        assert categorize("unknown", False) == Category.EXEC

    def test_extract_target_bash(self):
        tc = ToolCall(name="bash", input='{"command": "git status"}', id="1")
        target, is_file, ok = extract_target(tc)
        assert target == "git status"
        assert not is_file
        assert ok

    def test_extract_target_invalid_json(self):
        tc = ToolCall(name="read_file", input="not json", id="1")
        _, _, ok = extract_target(tc)
        assert not ok


class TestEngine:
    def test_mode_fallback_matrix(self):
        assert mode_fallback(Mode.DEFAULT, Category.READ) == Decision.ALLOW
        assert mode_fallback(Mode.DEFAULT, Category.WRITE) == Decision.ASK
        assert mode_fallback(Mode.DEFAULT, Category.EXEC) == Decision.ASK
        assert mode_fallback(Mode.ACCEPT_EDITS, Category.WRITE) == Decision.ALLOW
        assert mode_fallback(Mode.BYPASS, Category.EXEC) == Decision.ALLOW
        assert mode_fallback(Mode.PLAN, Category.WRITE) == Decision.ASK
        assert mode_fallback(Mode.PLAN, Category.EXEC) == Decision.ASK

    def test_check_blacklist(self, tmp_path):
        engine, _ = new_engine(str(tmp_path))
        tc = ToolCall(name="bash", input='{"command": "rm -rf /"}', id="1")
        dec, reason = engine.check(Mode.BYPASS, tc, False)
        assert dec == Decision.DENY
        assert "黑名单" in reason

    def test_check_sandbox(self, tmp_path):
        engine, _ = new_engine(str(tmp_path))
        tc = ToolCall(name="read_file", input='{"path": "/etc/passwd"}', id="1")
        dec, reason = engine.check(Mode.DEFAULT, tc, True)
        assert dec == Decision.DENY
        assert "项目目录之外" in reason

    def test_check_allow_read(self, tmp_path):
        root = str(tmp_path)
        (tmp_path / "test.txt").write_text("hi")
        engine, _ = new_engine(root)
        tc = ToolCall(name="read_file", input=f'{{"path": "{tmp_path / "test.txt"}"}}', id="1")
        dec, _ = engine.check(Mode.DEFAULT, tc, True)
        assert dec == Decision.ALLOW

    def test_check_ask_write_default(self, tmp_path):
        engine, _ = new_engine(str(tmp_path))
        tc = ToolCall(
            name="write_file",
            input=f'{{"path": "{tmp_path / "new.txt"}", "content": "hi"}}',
            id="1",
        )
        dec, _ = engine.check(Mode.DEFAULT, tc, False)
        assert dec == Decision.ASK

    def test_check_allow_write_accept_edits(self, tmp_path):
        engine, _ = new_engine(str(tmp_path))
        tc = ToolCall(
            name="write_file",
            input=f'{{"path": "{tmp_path / "new.txt"}", "content": "hi"}}',
            id="1",
        )
        dec, _ = engine.check(Mode.ACCEPT_EDITS, tc, False)
        assert dec == Decision.ALLOW

    def test_parse_mode(self):
        m, ok = parse_mode("default")
        assert ok and m == Mode.DEFAULT
        m, ok = parse_mode("acceptEdits")
        assert ok and m == Mode.ACCEPT_EDITS
        m, ok = parse_mode("bypassPermissions")
        assert ok and m == Mode.BYPASS
        m, ok = parse_mode("unknown")
        assert not ok and m == Mode.DEFAULT

    def test_next_mode_cycle(self):
        assert next_mode(Mode.DEFAULT) == Mode.ACCEPT_EDITS
        assert next_mode(Mode.BYPASS) == Mode.DEFAULT


class TestPersist:
    def test_rule_for_bash(self, tmp_path):
        from micodeagent.permission.persist import rule_for

        tc = ToolCall(name="bash", input='{"command": "git status"}', id="1")
        rule, rule_str, ok = rule_for(tc, str(tmp_path))
        assert ok
        assert rule.tool == "Bash"

    def test_persist_local_allow(self, tmp_path):
        from micodeagent.permission.persist import persist_local_allow

        engine, _ = new_engine(str(tmp_path))
        tc = ToolCall(name="bash", input='{"command": "git status"}', id="1")
        persist_local_allow(engine, tc)
        # 重新加载引擎，该命令应 ALLOW
        engine2, _ = new_engine(str(tmp_path))
        dec, _ = engine2.check(Mode.DEFAULT, tc, False)
        assert dec == Decision.ALLOW
