"""conversation 模块单测"""

from micodeagent.conversation import Conversation
from micodeagent.llm import ROLE_ASSISTANT, ROLE_TOOL, ToolCall, ToolResult


class TestConversation:
    def test_initial_empty(self):
        conv = Conversation()
        assert conv.messages() == []

    def test_add_user(self):
        conv = Conversation()
        conv.add_user("你好")
        msgs = conv.messages()
        assert len(msgs) == 1
        assert msgs[0].role == "user"
        assert msgs[0].content == "你好"

    def test_add_assistant(self):
        conv = Conversation()
        conv.add_assistant("你好，有什么可以帮你")
        msgs = conv.messages()
        assert len(msgs) == 1
        assert msgs[0].role == "assistant"

    def test_round_trip_order(self):
        conv = Conversation()
        conv.add_user("第一问")
        conv.add_assistant("第一答")
        conv.add_user("第二问")
        conv.add_assistant("第二答")
        msgs = conv.messages()
        assert [m.role for m in msgs] == ["user", "assistant", "user", "assistant"]
        assert [m.content for m in msgs] == ["第一问", "第一答", "第二问", "第二答"]

    def test_messages_returns_copy(self):
        conv = Conversation()
        conv.add_user("hi")
        msgs = conv.messages()
        msgs.clear()
        # 内部历史不受返回副本影响
        assert len(conv.messages()) == 1

    def test_tool_call_round(self):
        """工具调用 + 结果 + 续答的完整角色序列。"""
        conv = Conversation()
        conv.add_user("读文件")
        conv.add_assistant_with_tool_calls(
            "我来读",
            [ToolCall(id="c1", name="read_file", input='{"path": "x"}')],
        )
        conv.add_tool_results([ToolResult(tool_call_id="c1", content="内容", is_error=False)])
        conv.add_assistant("文件内容是...")

        msgs = conv.messages()
        assert len(msgs) == 4
        assert [m.role for m in msgs] == ["user", ROLE_ASSISTANT, ROLE_TOOL, ROLE_ASSISTANT]
        # 工具调用回合
        assert msgs[1].tool_calls[0].name == "read_file"
        assert msgs[1].tool_calls[0].input == '{"path": "x"}'
        # 工具结果回合
        assert msgs[2].tool_results[0].tool_call_id == "c1"
        assert msgs[2].tool_results[0].content == "内容"

    def test_last_role(self):
        """last_role 返回最后一条消息的 role，空历史返回空串。"""
        conv = Conversation()
        assert conv.last_role() == ""
        conv.add_user("hi")
        assert conv.last_role() == "user"
        conv.add_assistant("hello")
        assert conv.last_role() == "assistant"
        conv.add_assistant_with_tool_calls(
            "读文件", [ToolCall(id="c1", name="read_file", input="{}")]
        )
        assert conv.last_role() == "assistant"
        conv.add_tool_results([ToolResult(tool_call_id="c1", content="x")])
        assert conv.last_role() == "tool"
