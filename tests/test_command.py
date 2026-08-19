"""slash 命令体系单测"""

import pytest

from micodeagent.command import Command, Kind, Registry, parse
from micodeagent.command.builtins import register_builtins
from micodeagent.command.ui import NopUI


def _cmd(name: str, kind: Kind = Kind.LOCAL) -> Command:
    async def _h(ui):
        pass

    return Command(name=name, description="d", kind=kind, handler=_h)


class TestRegistry:
    def test_register_ok(self):
        r = Registry()
        r.register(_cmd("help"))
        assert r.lookup("help") is not None

    def test_register_duplicate_raises(self):
        r = Registry()
        r.register(_cmd("help"))
        with pytest.raises(RuntimeError, match="conflict"):
            r.register(_cmd("help"))

    def test_register_alias_conflict(self):
        r = Registry()
        c1 = _cmd("help")
        c1.aliases = ["h"]
        r.register(c1)
        c2 = _cmd("h")
        with pytest.raises(RuntimeError, match="conflict"):
            r.register(c2)

    def test_visible_sorted(self):
        r = Registry()
        r.register(_cmd("zebra"))
        r.register(_cmd("apple"))
        r.register(_cmd("mango"))
        assert [c.name for c in r.visible()] == ["apple", "mango", "zebra"]

    def test_prefix_match(self):
        r = Registry()
        r.register(_cmd("status"))
        r.register(_cmd("session"))
        r.register(_cmd("help"))
        assert [c.name for c in r.prefix_match("s")] == ["session", "status"]

    def test_lookup_case_insensitive(self):
        r = Registry()
        r.register(_cmd("help"))
        assert r.lookup("HELP") is not None
        assert r.lookup("Help") is not None


class TestParse:
    def test_parse_cases(self):
        assert parse("") == ("", False)
        assert parse("   ") == ("", False)
        assert parse("hello") == ("", False)
        assert parse("/") == ("", True)
        assert parse("/help") == ("help", True)
        assert parse("  /HELP  ") == ("help", True)
        assert parse("/help xx") == ("", True)
        assert parse("/help  ") == ("help", True)


class TestBuiltins:
    def test_register_builtins_count(self):
        r = Registry()
        register_builtins(r)
        assert len(r.visible()) == 12
        names = [c.name for c in r.visible()]
        expected = [
            "clear",
            "compact",
            "do",
            "exit",
            "help",
            "memory",
            "permission",
            "plan",
            "resume",
            "review",
            "session",
            "status",
        ]
        assert names == expected

    @pytest.mark.asyncio
    async def test_handlers_run_on_nop_ui(self):
        r = Registry()
        register_builtins(r)
        ui = NopUI()
        for c in r.visible():
            await c.handler(ui)  # 不应抛异常

    @pytest.mark.asyncio
    async def test_handle_status(self):
        from micodeagent.command.builtin_local import handle_status

        class Recording(NopUI):
            def __init__(self):
                self.msgs = []

            def println(self, msg):
                self.msgs.append(msg)

        ui = Recording()
        await handle_status(ui)
        assert len(ui.msgs) == 1
        for key in ["Mode", "Tokens", "Tools", "Memories", "Model", "Directory"]:
            assert key in ui.msgs[0]

    @pytest.mark.asyncio
    async def test_handle_do(self):
        from micodeagent.command.builtin_prompt import handle_do
        from micodeagent.permission import Mode

        class Recording(NopUI):
            def __init__(self):
                self.set_calls = []
                self.inject_calls = []

            def set_mode(self, m):
                self.set_calls.append(m)

            def inject_and_send(self, label, preset):
                self.inject_calls.append((label, preset))

        ui = Recording()
        await handle_do(ui)
        assert ui.set_calls == [Mode.DEFAULT]
        assert len(ui.inject_calls) == 1
