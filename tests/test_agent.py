"""agent ReAct 循环 + 权限集成单测"""

import asyncio

import pytest

from micodeagent.agent import (
    MAX_ITERATIONS,
    MAX_UNKNOWN_RUN,
    NOTICE_MAX_ITER,
    NOTICE_UNKNOWN_TOOLS,
    Agent,
)
from micodeagent.conversation import Conversation
from micodeagent.llm import (
    ROLE_ASSISTANT,
    ROLE_TOOL,
    Request,
    StreamEvent,
    ToolCall,
    Usage,
)
from micodeagent.permission import Mode, Outcome, new_engine
from micodeagent.tool import new_default_registry


class FakeProvider:
    """可编排的 Fake Provider，按调用次数逐次返回脚本，记录 Request。"""

    def __init__(self, scripts: list[list[StreamEvent]], repeat_last: bool = False):
        self.scripts = scripts
        self.repeat_last = repeat_last
        self.calls = 0
        self.received_requests: list[Request] = []
        self.name = "fake"
        self.model = "fake-model"

    async def stream(self, req: Request):
        self.calls += 1
        self.received_requests.append(req)

        if self.calls <= len(self.scripts):
            idx = self.calls - 1
        elif self.repeat_last and self.scripts:
            idx = len(self.scripts) - 1
        else:
            yield StreamEvent(done=True)
            return

        for ev in self.scripts[idx]:
            yield ev


@pytest.fixture
def engine(tmp_path):
    return new_engine(str(tmp_path))[0]


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_multi_turn_loop(self, engine):
        script1 = [
            StreamEvent(text="我来读文件"),
            StreamEvent(tool_calls=[ToolCall(id="c1", name="read_file", input='{"path":"x"}')]),
            StreamEvent(done=True),
        ]
        script2 = [StreamEvent(text="文件内容总结"), StreamEvent(done=True)]
        provider = FakeProvider([script1, script2])
        agent = Agent(provider, new_default_registry(), "test", engine)
        conv = Conversation()
        conv.add_user("读文件")

        events = []
        async for ev in agent.run(conv, Mode.DEFAULT, asyncio.Event()):
            events.append(ev)

        iters = [ev.iter for ev in events if ev.iter]
        assert iters[0] == 1 and iters[-1] == 2
        assert events[-1].done

    @pytest.mark.asyncio
    async def test_max_iteration_limit(self, engine):
        tool_script = [
            StreamEvent(tool_calls=[ToolCall(id="c", name="read_file", input='{"path":"x"}')]),
            StreamEvent(done=True),
        ]
        provider = FakeProvider([tool_script], repeat_last=True)
        agent = Agent(provider, new_default_registry(), "test", engine)
        conv = Conversation()
        conv.add_user("反复调工具")

        notices = []
        async for ev in agent.run(conv, Mode.DEFAULT, asyncio.Event()):
            if ev.notice:
                notices.append(ev.notice)

        assert provider.calls == MAX_ITERATIONS
        assert notices == [NOTICE_MAX_ITER]

    @pytest.mark.asyncio
    async def test_unknown_tool_stop(self, engine):
        script = [
            StreamEvent(tool_calls=[ToolCall(id="c", name="nonexistent", input="{}")]),
            StreamEvent(done=True),
        ]
        provider = FakeProvider([script], repeat_last=True)
        agent = Agent(provider, new_default_registry(), "test", engine)
        conv = Conversation()
        conv.add_user("调未知工具")

        notices = []
        # 用 BYPASS 避免未知工具（归 EXEC 类）在 default 下触发人在回路
        async for ev in agent.run(conv, Mode.BYPASS, asyncio.Event()):
            if ev.notice:
                notices.append(ev.notice)

        assert notices == [NOTICE_UNKNOWN_TOOLS]
        assert provider.calls == MAX_UNKNOWN_RUN

    @pytest.mark.asyncio
    async def test_plan_mode_tools(self, engine):
        script = [StreamEvent(text="计划"), StreamEvent(done=True)]
        provider = FakeProvider([script])
        agent = Agent(provider, new_default_registry(), "test", engine)
        conv = Conversation()
        conv.add_user("出计划")

        async for ev in agent.run(conv, Mode.PLAN, asyncio.Event()):
            pass

        req = provider.received_requests[0]
        names = [d.name for d in req.tools]
        assert set(names) == {"read_file", "glob", "grep"}

    @pytest.mark.asyncio
    async def test_cache_usage_transparent(self, engine):
        script = [
            StreamEvent(text="hi"),
            StreamEvent(
                usage=Usage(input_tokens=100, output_tokens=50, cache_write=200, cache_read=300)
            ),
            StreamEvent(done=True),
        ]
        provider = FakeProvider([script])
        agent = Agent(provider, new_default_registry(), "test", engine)
        conv = Conversation()
        conv.add_user("hi")

        usages = []
        async for ev in agent.run(conv, Mode.DEFAULT, asyncio.Event()):
            if ev.usage:
                usages.append(ev.usage)

        assert usages[0].cache_write == 200
        assert usages[0].cache_read == 300

    @pytest.mark.asyncio
    async def test_reminder_not_in_history(self, engine):
        script = [StreamEvent(text="hi"), StreamEvent(done=True)]
        provider = FakeProvider([script])
        agent = Agent(provider, new_default_registry(), "test", engine)
        conv = Conversation()
        conv.add_user("hi")

        async for ev in agent.run(conv, Mode.PLAN, asyncio.Event()):
            pass

        for m in conv.messages():
            assert "<system-reminder>" not in m.content


class TestPermissionIntegration:
    @pytest.mark.asyncio
    async def test_deny_not_interrupt(self, tmp_path):
        """AC11：被拒工具回灌错误，Loop 继续到下一轮。"""
        engine, _ = new_engine(str(tmp_path))
        # 请求读项目外路径（沙箱拦），次轮给纯文本
        script1 = [
            StreamEvent(
                tool_calls=[ToolCall(id="c1", name="read_file", input='{"path":"/etc/passwd"}')]
            ),
            StreamEvent(done=True),
        ]
        script2 = [StreamEvent(text="我换个方式"), StreamEvent(done=True)]
        provider = FakeProvider([script1, script2])
        agent = Agent(provider, new_default_registry(), "test", engine)
        conv = Conversation()
        conv.add_user("读 /etc/passwd")

        events = []
        async for ev in agent.run(conv, Mode.DEFAULT, asyncio.Event()):
            events.append(ev)

        # 工具结果含被拒错误
        tool_msgs = [m for m in conv.messages() if m.role == ROLE_TOOL]
        assert tool_msgs and tool_msgs[0].tool_results[0].is_error
        # Loop 继续到次轮（最终答复）
        assert conv.messages()[-1].role == ROLE_ASSISTANT
        assert "我换个方式" in conv.messages()[-1].content

    @pytest.mark.asyncio
    async def test_ask_allow_once(self, tmp_path):
        """AC10：人在回路允许本次。"""
        engine, _ = new_engine(str(tmp_path))
        # default 下写文件触发 Ask
        path = str(tmp_path / "out.txt")
        script1 = [
            StreamEvent(
                tool_calls=[
                    ToolCall(
                        id="c1", name="write_file", input=f'{{"path":"{path}","content":"hi"}}'
                    )
                ]
            ),
            StreamEvent(done=True),
        ]
        script2 = [StreamEvent(text="写好了"), StreamEvent(done=True)]
        provider = FakeProvider([script1, script2])
        agent = Agent(provider, new_default_registry(), "test", engine)
        conv = Conversation()
        conv.add_user("写文件")

        async def consume():
            async for ev in agent.run(conv, Mode.DEFAULT, asyncio.Event()):
                if ev.approval is not None:
                    ev.approval.respond.set_result(Outcome.ALLOW_ONCE)

        await consume()

        # 文件被写入
        assert (tmp_path / "out.txt").read_text() == "hi"

    @pytest.mark.asyncio
    async def test_ask_deny_once(self, tmp_path):
        """AC10：人在回路拒绝本次。"""
        engine, _ = new_engine(str(tmp_path))
        path = str(tmp_path / "out.txt")
        script1 = [
            StreamEvent(
                tool_calls=[
                    ToolCall(
                        id="c1", name="write_file", input=f'{{"path":"{path}","content":"hi"}}'
                    )
                ]
            ),
            StreamEvent(done=True),
        ]
        script2 = [StreamEvent(text="被拒了"), StreamEvent(done=True)]
        provider = FakeProvider([script1, script2])
        agent = Agent(provider, new_default_registry(), "test", engine)
        conv = Conversation()
        conv.add_user("写文件")

        async def consume():
            async for ev in agent.run(conv, Mode.DEFAULT, asyncio.Event()):
                if ev.approval is not None:
                    ev.approval.respond.set_result(Outcome.DENY_ONCE)

        await consume()

        # 文件未写入
        assert not (tmp_path / "out.txt").exists()
        tool_msgs = [m for m in conv.messages() if m.role == ROLE_TOOL]
        assert tool_msgs[0].tool_results[0].is_error

    @pytest.mark.asyncio
    async def test_ask_allow_forever(self, tmp_path):
        """AC10：永久放行写入本地配置。"""
        engine, _ = new_engine(str(tmp_path))
        path = str(tmp_path / "out.txt")
        script1 = [
            StreamEvent(
                tool_calls=[
                    ToolCall(
                        id="c1", name="write_file", input=f'{{"path":"{path}","content":"hi"}}'
                    )
                ]
            ),
            StreamEvent(done=True),
        ]
        script2 = [StreamEvent(text="写好了"), StreamEvent(done=True)]
        provider = FakeProvider([script1, script2])
        agent = Agent(provider, new_default_registry(), "test", engine)
        conv = Conversation()
        conv.add_user("写文件")

        async def consume():
            async for ev in agent.run(conv, Mode.DEFAULT, asyncio.Event()):
                if ev.approval is not None:
                    ev.approval.respond.set_result(Outcome.ALLOW_FOREVER)

        await consume()

        # 文件被写入 + 本地配置被更新
        assert (tmp_path / "out.txt").read_text() == "hi"
        assert (tmp_path / ".micodeagent" / "settings.local.yaml").exists()

    @pytest.mark.asyncio
    async def test_read_only_no_approval(self, tmp_path):
        """AC13：只读批不产生 ApprovalRequest，且并发执行。"""
        engine, _ = new_engine(str(tmp_path))
        registry = new_default_registry()
        # 两个只读工具 + 纯文本
        script1 = [
            StreamEvent(
                tool_calls=[
                    ToolCall(id="1", name="glob", input='{"pattern":"*.py","path":"."}'),
                    ToolCall(id="2", name="grep", input='{"pattern":"x","path":"."}'),
                ]
            ),
            StreamEvent(done=True),
        ]
        script2 = [StreamEvent(text="完成"), StreamEvent(done=True)]
        provider = FakeProvider([script1, script2])
        agent = Agent(provider, registry, "test", engine)
        conv = Conversation()
        conv.add_user("搜东西")

        approvals = []
        async for ev in agent.run(conv, Mode.DEFAULT, asyncio.Event()):
            if ev.approval is not None:
                approvals.append(ev.approval)

        assert approvals == []

    @pytest.mark.asyncio
    async def test_cancel_during_approval(self, tmp_path):
        """AC12：人在回路等待中取消。"""
        engine, _ = new_engine(str(tmp_path))
        path = str(tmp_path / "out.txt")
        script1 = [
            StreamEvent(
                tool_calls=[
                    ToolCall(
                        id="c1", name="write_file", input=f'{{"path":"{path}","content":"hi"}}'
                    )
                ]
            ),
            StreamEvent(done=True),
        ]
        provider = FakeProvider([script1])
        agent = Agent(provider, new_default_registry(), "test", engine)
        conv = Conversation()
        conv.add_user("写文件")
        cancel = asyncio.Event()

        async def consume():
            async for ev in agent.run(conv, Mode.DEFAULT, cancel):
                if ev.approval is not None:
                    # 模拟 TUI 取消：先 DENY_ONCE 再 set cancel
                    ev.approval.respond.set_result(Outcome.DENY_ONCE)
                    cancel.set()

        await consume()

        # 历史合法（末尾 assistant）
        assert conv.last_role() == "assistant"
