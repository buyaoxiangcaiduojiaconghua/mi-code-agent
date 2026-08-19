# MCP 客户端 Tasks

> 基于已批准的 spec.md + plan.md。任务有序，每步留绿。验证一律「先跑命令看输出，再下结论」。

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 改   | `pyproject.toml` | `dependencies` 增加 `"mcp>=1.0"`；`uv sync` / `pip install -e .` 同步 |
| 新建 | `src/micodeagent/mcp/__init__.py` | 暴露 `Config` / `ServerConfig` / `Manager` / `load_config` / `new_manager` |
| 新建 | `src/micodeagent/mcp/config.py` | `Config` / `ServerConfig`、`load_config`、`_load_file`、`_expand_vars`、`_apply_expansion`、`_merge_servers`、`_validate_server` |
| 新建 | `tests/test_mcp_config.py` | 两层合并 / `${VAR}` 展开 / 字段校验 / 降级 单测 |
| 新建 | `src/micodeagent/mcp/tool.py` | `CallerSession` Protocol、`McpTool`、`adapt_tool`、`execute`、非 text 块告警 once set |
| 新建 | `tests/test_mcp_tool.py` | 命名拼接 / 禁用字符 / Execute 成功 / 远端 IsError / 超时 / 协议错 / 非 text 块跳过 单测 |
| 新建 | `src/micodeagent/mcp/manager.py` | `Manager`、`_Session`、`new_manager`（`asyncio.gather` 并发 + 30s 超时）、`close`（5s 兜底）、`tools`；模块级 `connect_timeout` / `close_timeout` |
| 新建 | `tests/test_mcp_manager.py` | 连接成功 / 失败 / 超时、`close` 不死锁、并发写共享状态安全 单测 |
| 改   | `src/micodeagent/cli.py` | 装配 `load_config`、`new_manager`、注册 MCP 工具、`finally: await mgr.close()` |
| 新建 | `docs/ch07-mcp/mcp-servers.example.yaml` | 配置示例（含 stdio / http 各一个，用 `${VAR}`） |

---

## T1: 添加 MCP Python SDK 依赖

**文件：** `pyproject.toml`、`uv.lock`（自动生成）
**依赖：** 无
**步骤：**
1. 在 `[project]` 的 `dependencies` 列表追加 `"mcp>=1.0"`。
2. 在仓库根执行 `uv sync`（或 `pip install -e .`）；查看 `uv.lock` 或 `pip list` 确认 `mcp` 与其传递依赖（`pydantic` 等）已装好。
3. 写一段最小试导入：
   ```python
   from mcp import ClientSession, StdioServerParameters
   from mcp.client.stdio import stdio_client
   from mcp.client.streamable_http import streamablehttp_client
   import mcp.types as mtypes
   ```
   并在 Python REPL 跑一次 `import micodeagent.mcp` 雏形，验证可用。

**验证：** `python -c "import mcp"` 输出非错误；`uv pip list | grep mcp` 看到包名。

## T2: 配置类型与加载（含两层合并 + 变量展开 + 字段校验）

**文件：** `src/micodeagent/mcp/config.py`、`src/micodeagent/mcp/__init__.py`、`tests/test_mcp_config.py`
**依赖：** T1
**步骤：**
1. 定义对外类型 `ServerConfig`、`Config`（见 plan.md「核心数据结构」），用 `@dataclass`。
2. 定义内部 `@dataclass class _RawServer`（含全部字段，全部带默认值）。
3. `_load_file(path)`：不存在→`{}`；`yaml.safe_load` 失败→stderr 告警 + `{}`；取 `mcp_servers` 段。
4. `_expand_vars(s)`：正则 `\$\{([A-Za-z_][A-Za-z0-9_]*)\}`，`os.environ.get` 取值，未定义记录。
5. `_apply_expansion(name, srv)`：对 env/headers 值展开；未定义变量 stderr 告警（同 server 同变量限一次）。
6. `_merge_servers(user, project)`：先 update user 再 update project（同名整对象覆盖）。
7. `_validate_server(name, srv)`：type 必为 stdio/http；stdio 必填 command、http 必填 url；违规跳过 + 告警。
8. `load_config(root)`：用户级 `~/.micodeagent/config.yaml`、项目级 `<root>/.micodeagent.yaml`；两层加载 + 展开 + 合并 + 校验；永不抛出。
9. `__init__.py` 中 `from .config import Config, ServerConfig, load_config`。

**验证：** `pytest tests/test_mcp_config.py` 覆盖：两文件缺失→空；同名 server 项目级胜出；非法 YAML 跳过；`${VAR}` 展开/未定义空串+告警；command 不展开；字段校验跳过。

## T3: 工具适配（McpTool）

**文件：** `src/micodeagent/mcp/tool.py`、`tests/test_mcp_tool.py`
**依赖：** T1
**步骤：**
1. `import mcp.types as mtypes`；`from micodeagent.tool import Result`（或对应内置工具协议路径）。
2. 定义最小 Protocol `CallerSession` 与 `@dataclass class McpTool`（见 plan.md）。
3. 实现 Tool 协议要求的属性/方法：`name`（返回 full_name）、`description`、`parameters`、`read_only`、`async def execute(args)`。
4. `adapt_tool(server_name, t, session)`：`full_name = f"mcp__{server_name}__{t.name}"`；`_VALID_NAME` 校验；description 兜底；schema 透传；read_only 来自 readOnlyHint。
5. `execute(args)`：`asyncio.wait_for(caller.call_tool(...), 30)`；TextContent 拼接；isError 映射；非 text 块丢弃 + 告警一次。

**验证：** `pytest tests/test_mcp_tool.py` 覆盖：命名拼接/禁用字符/execute 各分支（成功/远端 IsError/超时/协议错/非 text 块）。

## T4: 连接管理器（Manager）

**文件：** `src/micodeagent/mcp/manager.py`、`src/micodeagent/mcp/__init__.py`、`tests/test_mcp_manager.py`
**依赖：** T2、T3
**步骤：**
1. 模块级变量 `connect_timeout: float = 30.0`、`close_timeout: float = 5.0`。
2. 定义 `_Session` 与 `Manager`（含 `_stack`、`_lock`）。
3. `new_manager(cfg, version)`：`asyncio.gather` 并发 `_connect_one`；完成后排序 `_tools`。
4. `_connect_one`：`asyncio.wait_for(_do_connect, connect_timeout)`；超时/异常 stderr 告警。
5. `_do_connect`：按 type 构造 transport；`_stack.enter_async_context` 进入；`session.initialize()` + `session.list_tools()`；adapt_tool 收齐；lock 内 append。
6. `tools()`：返回 `list(self._tools)` 副本。
7. `close()`：`asyncio.wait_for(_stack.aclose(), close_timeout)`；超时 stderr 告警。
8. `__init__.py` 追加 `from .manager import Manager, new_manager`、`from .tool import McpTool`。

**验证：** `pytest tests/test_mcp_manager.py` 覆盖：空 cfg→空 tools；失败隔离；超时收尾；close 兜底；并发安全。

## T5: cli 接线

**文件：** `src/micodeagent/cli.py`
**依赖：** T2、T3、T4
**步骤：**
1. import `asyncio`、`micodeagent.mcp as mcp_client`。
2. 拆为 `async def _amain() -> int` + `def main() -> None: raise SystemExit(asyncio.run(_amain()))`。
3. registry 后插入 mcp 装配：`load_config` → `new_manager` → 注册工具 → finally `close`。
4. `root` 复用 `os.getcwd()`；`version` 复用 `__version__`。

**验证：** `python -m micodeagent` 无 MCP 配置进 TUI；command 不存在 server 进 TUI 不阻塞。

## T6: 配置示例

**文件：** `docs/ch07-mcp/mcp-servers.example.yaml`
**依赖：** 无（可与 T2 并行）
**步骤：** 写 stdio/http 各一个示例，用 `${VAR}`。

**验证：** 在 `tests/test_mcp_config.py` 增加用例读取示例文件断言三个 server 解析成功。

## T7: tmux 端到端实跑

**依赖：** T1–T6
**步骤：** 配 `@modelcontextprotocol/server-everything`；调用 echo 工具；永久放行；bypass 黑名单兜底；退出子进程终止。

## T8: 全量编译测试与规范

**依赖：** T1–T7
**步骤：** `ruff format --check` / `ruff check` / `pytest` / 凭据不落盘检索。

## 执行顺序

```
T1(SDK 依赖) ─┬─→ T2(config) ─┐
              │                ├─→ T4(manager) ─→ T5(cli 接线) ─→ T7(tmux 实跑) ─→ T8(规范)
              └─→ T3(tool)   ─┘
                                 └─→ T6(配置示例)（可与 T2 并行）
```
