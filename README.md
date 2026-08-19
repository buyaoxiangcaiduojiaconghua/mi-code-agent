# MiCodeAgent

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License MIT">
  <img src="https://img.shields.io/badge/Test-251%20passed-brightgreen.svg" alt="Tests">
  <img src="https://img.shields.io/badge/Textual-8.x-purple.svg" alt="Textual">
</p>

> 一个终端 AI 编程助手（类似 Claude Code），用 Python + Textual 构建。
> 从「只能聊天」到「能在安全护栏内自主干活的 Agent」，再到「多 Agent 团队协作」。

```
  /\_/\
 ( o.o )
  > ^ <
```

---

## 目录

- [核心特性](#-核心特性)
- [快速开始](#-快速开始)
- [使用指南](#-使用指南)
- [配置详解](#-配置详解)
- [扩展能力](#-扩展能力)
- [架构](#-架构)
- [开发](#-开发)
- [项目演进](#-项目演进)
- [常见问题](#-常见问题)

---

## ✨ 核心特性

### 🤖 自主 Agent

- **ReAct 循环**：想 → 调工具 → 看结果 → 边做边调整，直到任务完成，最大 25 轮兜底
- **保序分批并发**：一次回复的多个工具调用，连续只读并发执行、有副作用串行执行
- **流式输出**：回复逐字实时呈现，支持 Anthropic 扩展思考（extended thinking）
- **多轮上下文**：单会话内完整历史，跨轮引用前文

### 🔧 工具生态

| 能力 | 说明 |
|------|------|
| 内置工具 | 读文件、写文件、改文件、执行命令、按模式找文件、搜代码内容 |
| MCP 客户端 | 自动发现并注册外部 MCP Server 工具（stdio + Streamable HTTP），命名空间 `mcp__<server>__<tool>` |
| Skill 技能包 | 可复用 AI 操作封装成 Markdown，两阶段加载，按需激活，支持热更新 |
| 子 Agent | 定义式（固定角色）/ Fork 式（继承父对话），跑到底模式，后台任务 |
| 团队协作 | 长期小组、点对点消息、共享任务清单、Coordinator 模式 |

### 🛡️ 安全与可靠性

- **五层权限**：危险命令黑名单 → 路径沙箱 → 可配置规则 → 权限模式 → 人在回路
- **四档模式**：`default` / `acceptEdits` / `plan` / `bypassPermissions`，Shift+Tab 切换
- **上下文管理**：两层压缩（工具结果落盘 + LLM 摘要），长时间工作不撑爆窗口
- **Hook 生命周期**：事件 + 条件 + 动作三要素，工具执行前可拦截
- **Worktree 隔离**：子 Agent 并行干活用 git worktree 隔离文件修改

### 🎨 体验优化

- **slash 命令**：13 个内置命令 + Tab 补全
- **会话持久化**：JSONL 追加写，`/resume` 恢复历史会话
- **自动记忆**：从对话自动提取用户偏好、项目知识，跨会话注入

---

## 🚀 快速开始

### 环境要求

- Python 3.12+
- macOS / Linux

### 安装

```bash
# 克隆仓库
git clone https://github.com/buyaoxiangcaiduojiaconghua/mi-code-agent.git
cd mi-code-agent

# 创建虚拟环境并安装（含开发依赖）
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 配置

```bash
# 复制配置模板
cp .micodeagent/config.yaml.example .micodeagent/config.yaml
```

编辑 `.micodeagent/config.yaml`，填入 API Key：

```yaml
providers:
  - name: "deepseek-chat"
    protocol: "openai"          # openai 或 anthropic
    model: "deepseek-chat"
    base_url: "https://api.deepseek.com"
    api_key: "sk-你的key"
    context_window: 128000      # 可选，未配置时按协议默认
```

> ⚠️ `config.yaml` 已被 `.gitignore` 忽略，真实 key 不会提交到仓库。

### 启动

```bash
python -m micodeagent
# 或
micodeagent
```

启动后自动进入对话界面，输入问题即可。

---

## 📖 使用指南

### slash 命令

| 命令 | 说明 | 类型 |
|------|------|------|
| `/help` | 列出所有可用命令 | 本地 |
| `/status` | 显示运行状态（模式/用量/工具数） | 本地 |
| `/session` | 显示当前会话信息 | 本地 |
| `/memory` | 列出记忆文件 | 本地 |
| `/permission` | 显示当前权限模式 | 本地 |
| `/skill` | 列出可用 Skill | 本地 |
| `/plan` | 进入计划模式（只读工具） | 界面 |
| `/do` | 退出计划模式并按计划执行 | 提示词 |
| `/compact` | 手动压缩上下文 | 界面 |
| `/clear` | 清空当前会话 | 界面 |
| `/resume` | 恢复历史会话 | 界面 |
| `/review` | 审查代码变更 | 提示词 |
| `/exit` | 退出 | 界面 |

### 键盘操作

| 按键 | 功能 |
|------|------|
| `Enter` | 提交消息 |
| `Alt+Enter` | 插入换行（多行输入） |
| `Tab` | 触发命令补全 |
| `Shift+Tab` | 循环切换权限模式 |
| `Ctrl+C` | 流式中断当前轮 / 空闲时退出 |
| `Esc` | 取消当前轮 / 关闭补全菜单 |

### 权限模式

| 模式 | 只读 | 文件写 | 命令执行 |
|------|------|--------|----------|
| default | 放行 | 询问 | 询问 |
| acceptEdits | 放行 | 放行 | 询问 |
| plan | 放行 | 询问 | 询问 |
| bypassPermissions | 放行 | 放行 | 放行 |

> 危险命令黑名单和路径沙箱在 bypass 模式下依然生效。

---

## ⚙️ 配置详解

### 主配置 `.micodeagent/config.yaml`

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | 供应商标识名 |
| `protocol` | ✅ | `openai` 或 `anthropic` |
| `model` | ✅ | 模型名 |
| `api_key` | ✅ | 认证密钥，支持 `${VAR}` 环境变量展开 |
| `base_url` | ❌ | 自定义端点（兼容端点用） |
| `thinking` | ❌ | 是否启用扩展思考（仅 anthropic） |
| `context_window` | ❌ | 上下文窗口 token 数，默认 anthropic 200000 / openai 128000 |

### 权限配置 `.micodeagent/settings.yaml`

三层配置（优先级 本地 > 项目 > 用户）：

```yaml
default_mode: default

permissions:
  allow:
    - "Bash(git *)"
    - "Bash(pytest)"
  deny:
    - "Bash(rm *)"
    - "Read(.env)"
```

规则格式：`工具友好名(模式)`，支持精确匹配和 glob 匹配。

### 项目指令 `MEWCODE.md`

在项目根、`.micodeagent/`、`~/.micodeagent/` 各放一份，按优先级拼接，支持 `@include` 引用：

```markdown
# 项目规范
- 使用 Python 3.12
- 遵循 ruff 规范

@include rules/style.md
```

### MCP 配置 `.micodeagent.yaml`

```yaml
mcp_servers:
  github:
    type: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_TOKEN: "${GITHUB_TOKEN}"
```

### Hook 配置 `.micodeagent/hooks.yaml`

```yaml
hooks:
  - name: "block-rm"
    event: "PreToolUse"
    if:
      all_of:
        - match:
            field: "tool_name"
            type: "exact"
            value: "bash"
    action:
      type: "shell"
      command: "exit 2"
```

---

## 🧩 扩展能力

### Skill 技能包

在 `.micodeagent/skills/` 下创建 Markdown 文件：

```markdown
---
name: code-review
description: 审查代码变更并给出建议
mode: inline
---
你是代码审查专家。审查当前变更，指出潜在 bug、可读性问题和可简化处。
```

### 子 Agent 定义

在 `.micodeagent/agents/` 下创建：

```markdown
---
name: Explore
description: 只读代码探索 Agent
disallowedTools:
  - write_file
  - edit_file
model: haiku
maxTurns: 30
---
你是一个文件搜索专家。这是一个只读探索任务。
```

### 记忆系统

自动笔记分四类（用户偏好、纠正反馈、项目知识、参考资料），每 5 轮或用户显式要求时异步更新，索引注入后续会话。

---

## 🏗️ 架构

```
src/micodeagent/
├── agent/          # ReAct 循环引擎、子 Agent、Fork、后台任务
├── cli.py          # 入口装配
├── compact/        # 上下文管理（两层压缩）
├── command/        # slash 命令体系
├── config.py       # 配置加载
├── conversation.py # 会话历史
├── coordinator/    # Coordinator 模式
├── hook/           # Hook 生命周期系统
├── instructions/   # 项目指令加载
├── llm/            # LLM 协议层（Anthropic / OpenAI）
├── mcp/            # MCP 客户端
├── memory/         # 自动记忆
├── permission/     # 五层权限系统
├── prompt/         # 系统提示词工程化
├── session/        # 会话持久化（JSONL）
├── skills/         # Skill 技能包
├── subagent/       # 子 Agent 定义
├── task/           # 后台任务管理
├── team/           # 团队协作
├── tool/           # 工具系统
├── tui/            # Textual 终端界面
└── worktree/       # Worktree 隔离
```

### 依赖方向（无环）

```
tui → agent → {compact, hook, permission, tool, llm, conversation, subagent, task}
cli → {config, mcp, instructions, memory, session, skills, team, coordinator}
```

### 单次工具调用的数据流

```
agent.execute_batched(calls, mode)
  → engine.check(...)  # 五层权限判定
    → Allow → registry.execute(name, args)  # 执行工具
    → Ask   → 人在回路审批
    → Deny  → 结构化错误回灌
  → ToolResult 回灌对话历史
```

---

## 🧪 开发

### 运行测试

```bash
pytest tests/ -q          # 251 个单元测试
pytest tests/ -v          # 详细输出
```

### 代码规范

```bash
ruff check src/micodeagent tests
ruff format --check src/micodeagent tests
```

### 技术栈

| 组件 | 技术 |
|------|------|
| TUI | [Textual](https://textual.textualize.io/) + [Rich](https://github.com/Textualize/rich) |
| LLM SDK | [anthropic](https://github.com/anthropics/anthropic-sdk-python) / [openai](https://github.com/openai/openai-python) |
| MCP | [mcp](https://github.com/modelcontextprotocol/python-sdk) |
| 配置 | [PyYAML](https://pyyaml.org/) |
| 测试 | [pytest](https://docs.pytest.org/) + [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio) |
| 规范 | [ruff](https://github.com/astral-sh/ruff) |

---

## 🗺️ 项目演进

本项目通过 14 个章节（ch02 → ch15）逐步构建，每章对应一个能力维度，完整设计文档见 [`docs/`](docs/)：

| 章节 | 能力 | 目录 |
|------|------|------|
| ch02 | 纯对话客户端 | [`docs/ch02/`](docs/ch02/) |
| ch03 | 工具系统 | [`docs/ch03/`](docs/ch03/) |
| ch04 | Agent Loop（ReAct） | [`docs/ch04-agent-loop/`](docs/ch04-agent-loop/) |
| ch05 | 系统提示工程化 | [`docs/ch05-prompt-engineering/`](docs/ch05-prompt-engineering/) |
| ch06 | 五层权限系统 | [`docs/ch06-permission/`](docs/ch06-permission/) |
| ch07 | MCP 客户端 | [`docs/ch07-mcp/`](docs/ch07-mcp/) |
| ch08 | 上下文管理 | [`docs/ch08/`](docs/ch08/) |
| ch09 | 项目记忆与会话持久化 | [`docs/ch09/`](docs/ch09/) |
| ch10 | slash 命令体系 | [`docs/ch10/`](docs/ch10/) |
| ch11 | Skill 系统 | [`docs/ch11/`](docs/ch11/) |
| ch12 | Hook 系统 | [`docs/ch12/`](docs/ch12/) |
| ch13 | 子 Agent | [`docs/ch13/`](docs/ch13/) |
| ch14 | Worktree 隔离 | [`docs/ch14/`](docs/ch14/) |
| ch15 | Team 协作 | [`docs/ch15/`](docs/ch15/) |

---

## ❓ 常见问题

**Q: 支持哪些 LLM？**
A: Anthropic Claude 和所有 OpenAI 兼容端点（DeepSeek、OpenAI、通义、Kimi 等），通过 `protocol` 和 `base_url` 配置。

**Q: API key 会泄露吗？**
A: 不会。`config.yaml` 被 `.gitignore` 忽略，且支持 `${VAR}` 环境变量展开，key 无需写进配置文件。

**Q: 怎么让 Agent 更了解我的项目？**
A: 在项目根放 `MEWCODE.md`，写技术栈、代码规范、注意事项，启动时自动注入系统提示。

**Q: 支持多 Agent 并行吗？**
A: 支持。子 Agent 可用 Worktree 隔离并行干活，Team 协作模式可派生多个队员。

**Q: 会话能恢复吗？**
A: 能。会话以 JSONL 持久化，`/resume` 可恢复历史会话，自动记忆跨会话注入。

---

## 📄 许可证

[MIT](LICENSE)
