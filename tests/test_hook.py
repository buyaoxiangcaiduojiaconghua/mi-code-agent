"""Hook 系统单测"""

import pytest

from micodeagent.hook.engine import Engine
from micodeagent.hook.event import Event
from micodeagent.hook.executor import ExecutionResult, Executor
from micodeagent.hook.rule import (
    Action,
    ActionType,
    PromptAction,
    Rule,
    ShellAction,
)
from micodeagent.permission.matcher import compile_matcher


def _prompt_rule(name, event, text, **kw):
    return Rule(
        name=name,
        event=event,
        action=Action(type=ActionType.PROMPT, prompt=PromptAction(text=text)),
        **kw,
    )


class TestMatcher:
    @pytest.mark.parametrize(
        "pattern,is_cmd,hit,miss",
        [
            ("=git status", True, "git status", "git status -s"),
            ("~^npm (install|test)$", True, "npm install", "npm run dev"),
            ("!=foo", True, "bar", "foo"),
            ("!~^rm", True, "ls -lh", "rm -rf ."),
            ("!git *", True, "npm install", "git status"),
        ],
        ids=["exact", "regex", "not-exact", "not-regex", "not-glob"],
    )
    def test_matcher(self, pattern, is_cmd, hit, miss):
        m = compile_matcher(pattern, is_command=is_cmd)
        assert m.match(hit)
        assert not m.match(miss)

    def test_invalid_regex(self):
        with pytest.raises(ValueError):
            compile_matcher("~[invalid", is_command=True)

    def test_empty(self):
        with pytest.raises(ValueError):
            compile_matcher("", is_command=True)


class TestEngine:
    @pytest.mark.asyncio
    async def test_prompt_injection(self):
        engine = Engine([_prompt_rule("r1", Event.PRE_USER_MESSAGE, "reminder text")], [])
        result = await engine.dispatch(Event.PRE_USER_MESSAGE, {})
        assert result.injected_prompts == ["reminder text"]

    @pytest.mark.asyncio
    async def test_multiple_rules_order(self):
        engine = Engine(
            [
                _prompt_rule("r1", Event.STOP, "one"),
                _prompt_rule("r2", Event.STOP, "two"),
            ],
            [],
        )
        result = await engine.dispatch(Event.STOP, {})
        assert result.injected_prompts == ["one", "two"]

    @pytest.mark.asyncio
    async def test_only_once(self):
        engine = Engine([_prompt_rule("r1", Event.STOP, "x", only_once=True)], [])
        r1 = await engine.dispatch(Event.STOP, {})
        r2 = await engine.dispatch(Event.STOP, {})
        assert r1.injected_prompts == ["x"]
        assert r2.injected_prompts == []

    @pytest.mark.asyncio
    async def test_reset_only_once(self):
        engine = Engine([_prompt_rule("r1", Event.STOP, "x", only_once=True)], [])
        await engine.dispatch(Event.STOP, {})
        await engine.reset_for_new_session()
        r = await engine.dispatch(Event.STOP, {})
        assert r.injected_prompts == ["x"]

    @pytest.mark.asyncio
    async def test_blocking_stops(self):
        # 用 shell exit 2 拦截
        class BlockingExecutor:
            async def run(self, rule, payload, *, blocking):
                return ExecutionResult(
                    blocked=True,
                    reason="blocked",
                )

        engine = Engine(
            [
                Rule(
                    name="block",
                    event=Event.PRE_TOOL_USE,
                    action=Action(type=ActionType.SHELL, shell=ShellAction(command="x")),
                ),
                _prompt_rule("after", Event.PRE_TOOL_USE, "should-not-run"),
            ],
            [],
        )
        engine._executor = BlockingExecutor()
        result = await engine.dispatch(Event.PRE_TOOL_USE, {})
        assert result.blocked
        assert result.blocking_hook_name == "block"
        assert "should-not-run" not in result.injected_prompts


class TestExecutor:
    @pytest.mark.asyncio
    async def test_prompt(self):
        executor = Executor()
        rule = _prompt_rule("r", Event.STOP, "hello")
        result = await executor.run(rule, {}, blocking=False)
        assert result.prompt == "hello"

    @pytest.mark.asyncio
    async def test_shell_exit0(self):
        executor = Executor()
        rule = Rule(
            name="r",
            event=Event.STOP,
            action=Action(type=ActionType.SHELL, shell=ShellAction(command="exit 0")),
        )
        result = await executor.run(rule, {}, blocking=False)
        assert result.err is None
        assert not result.blocked

    @pytest.mark.asyncio
    async def test_shell_exit2_blocking(self):
        executor = Executor()
        rule = Rule(
            name="r",
            event=Event.PRE_TOOL_USE,
            action=Action(
                type=ActionType.SHELL, shell=ShellAction(command="echo blocked >&2; exit 2")
            ),
        )
        result = await executor.run(rule, {}, blocking=True)
        assert result.blocked
        assert "blocked" in result.reason

    @pytest.mark.asyncio
    async def test_shell_timeout(self):
        executor = Executor()
        rule = Rule(
            name="r",
            event=Event.STOP,
            action=Action(type=ActionType.SHELL, shell=ShellAction(command="sleep 2", timeout=0.1)),
        )
        result = await executor.run(rule, {}, blocking=False)
        assert isinstance(result.err, TimeoutError)
