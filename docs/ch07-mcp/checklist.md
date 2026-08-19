# MCP 客户端 Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为；括号内为验证方式与对应需求。

## 实现完整性
- [ ] 加载两层配置：两文件存在时按 server 名合并、同名 server 项目级完整覆盖用户级（验证：单测构造两层文件断言合并结果与字段来源）。(AC1/F1)
- [ ] 配置降级：任一文件缺失视为空、格式非法跳过该文件 + stderr 告警 + 其它正常加载，不致启动失败（验证：单测分别投喂缺失与非法 YAML，断言 `load_config` 不抛异常且其它层 server 仍在）。(AC1/N1)
- [ ] 字段校验：stdio 缺 command、http 缺 url、`type` 非法或缺失，均跳过该 server + stderr 给出原因，其它 server 不受影响（验证：单测分别构造各非法 server）。(AC2/N2)
- [ ] `${VAR}` 展开：env / headers 的值被展开；未定义变量展开为空串 + 一次性告警；command / args / 工具名 / server 名不展开（验证：单测覆盖各分支，含 `command: ${X}` 应保留字面量）。(AC3/F3)
- [ ] stdio 连接 + 握手 + 列工具：能拉起一个 MCP server 子进程并由 SDK 完成 `session.initialize()` + `session.list_tools()`；`env` 被注入到子进程环境（验证：用单测脚本启动一个最小 echo MCP server 或 tmux 实跑）。(AC4/F4/F6)
- [ ] HTTP 连接 + 自定义 headers：能对 HTTP MCP server 完成握手 + 列工具；`headers` 真正出现在每个 HTTP 请求中（验证：`pytest-httpx` 或 `httpx.MockTransport` 起一个最小 HTTP 端点 + 注入 `Authorization` 头，断言 server 端收到该头）。(AC5/F5/F6/N6)
- [ ] 工具命名：所有 MCP 工具的 `name` 形如 `mcp__<server>__<tool>`；前缀拼接后含 LLM 工具名禁用字符（非 `[A-Za-z0-9_-]`）的工具被跳过并告警（验证：单测构造含 `.` 的 server 名 / 工具名，断言 `adapt_tool` 返回 `None`）。(AC6/AC7/F8)
- [ ] 命名空间隔离：同一 tool 名在不同 server 互不覆盖；与 6 个内置工具天然不重名（验证：registry 注册后断言全名集合无重复）。(AC7/F8)
- [ ] 工具适配字段：description 空 → 兜底文案；schema 透传为 `dict[str, Any]`、空 schema 兜底 `{"type": "object"}`；`annotations.readOnlyHint==True` → `read_only is True`，其它（含 None / False）→ `False`（验证：单测覆盖各分支，含 `annotations is None` None-safe）。(AC6/F7)
- [ ] 调用结果聚合：`execute` 把远端多个 text content 块按顺序拼成 `content`；非 text 块静默丢弃 + 单 tool 限一次告警（验证：`test_mcp_tool` 注入 stub 返回混合内容块，断言 collected 仅含 text 且告警计数为 1）。(AC6/F7)
- [ ] 远端错误映射：远端 `isError==True` 时 `ToolResult.is_error is True`，`content` 仍为远端 text（验证：`test_mcp_tool` 注入 stub 返回 `isError=True` + text 块）。(AC6/F7)
- [ ] 协议错与超时回灌：`call_tool` 抛异常或 30s `asyncio.wait_for` 超时 → `is_error is True` 且 `content` 含可读错因，Agent Loop 不中断（验证：`test_mcp_tool` 注入 stub 抛异常 / 阻塞至超时）。(AC9/F7/F10/N5)
- [ ] 启动失败隔离：有 server 连接 / 握手 / 列工具失败时，只跳过它自身，其它 server 与内置工具集照常注册可用（验证：`test_mcp_manager` 用一个失败 server + 一个 stub 成功 server）。(AC8/F9/N1)
- [ ] 30s 启动超时：模拟连接卡住的 server 在超时窗口结束后被跳过（验证：`test_mcp_manager` 注入连接 stub + `monkeypatch` 缩短 timeout）。(AC8/F9/N1)
- [ ] 退出干净：`Manager.close()` 终止所有 stdio 子进程、断开 HTTP 会话；某 session 关闭卡住时 5s 兜底返回不阻塞（验证：`test_mcp_manager` 注入阻塞 fake 上下文 + 短兜底；tmux 实跑退出后 `ps` 无残留）。(AC10/F11/N7)

## 集成
- [ ] 权限链路自然命中：无规则时 `readOnlyHint=True` 的 MCP 工具走 Read 兜底、其余走 Exec 兜底；allow 规则 `mcp__<server>__*` 命中放行；bypass 放行（验证：`PermissionEngine` 对 mcp 全名调用断言裁决；tmux 实跑）。(AC11/F12/N4)
- [ ] permission 包零改动：`git diff src/micodeagent/permission/` 无任何修改。(N4)
- [ ] provider 适配层零改动：`src/micodeagent/llm/anthropic_provider.py`、`openai_provider.py` 无修改。(AC12/N3)
- [ ] 黑名单 / 沙箱对 MCP 工具自动跳过：`extract_target` 返回 `("", False, False)` → 黑名单不命中、沙箱不进入。(AC11/F12)
- [ ] 既有能力不退化：`pytest` 全过。(AC13/N5)

## 编译与测试
- [ ] `python -m micodeagent` 在合法配置下能进 TUI（含 / 不含 mcp 配置两种）。
- [ ] `ruff format --check .` 无 diff。
- [ ] `ruff check .` 无告警。
- [ ] `pytest` 通过（含 `tests/test_mcp_config.py` / `test_mcp_tool.py` / `test_mcp_manager.py`）。
- [ ] `pytest --asyncio-mode=auto tests/test_mcp_manager.py` 无悬挂 task / 死锁、无 `RuntimeWarning`。
- [ ] 凭据不落盘：`git grep` 无 token 明文。(AC14/N6)

## 端到端场景（tmux 实跑）
- [ ] 场景 1（无 MCP 配置）：正常进 TUI，registry 仅 6 内置工具。
- [ ] 场景 2（stdio server 接入）：连 server-everything，调 echo 工具，default 弹人在回路 → 允许本次 → 回灌 → 续答。
- [ ] 场景 3（失败隔离）：不存在 command 的 server + 能跑的 server，前者告警后者可用。
- [ ] 场景 4（永久放行 + 重启）：选永久 → settings.local.yaml 写入 → 重启不再弹窗。
- [ ] 场景 5（凭据展开）：`${VAR}` 未定义告警、定义后正常。
- [ ] 场景 6（退出干净）：退出后 ps 无残留子进程。
- [ ] 场景 7（bypass + 黑名单兜底）：bypass 下 MCP 不弹窗、内置 bash rm -rf / 仍被拦。
- [ ] 场景 8（HTTP server，可选）：headers 注入。
