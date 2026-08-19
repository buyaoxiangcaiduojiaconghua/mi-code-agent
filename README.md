# MiCodeAgent

> 一个终端 AI 编程助手（类似 Claude Code），用 Python + Textual 构建。

MiCodeAgent 是一个能自主干活的编码 Agent：它能读文件、写代码、执行命令、搜索代码，在五层安全护栏内多轮自主推进任务，还支持 MCP 工具生态、Skill 技能包、子 Agent 委派和团队协作。

```
  /\_/\
 ( o.o )
  > ^ <
```

---

## ✨ 核心特性

### 基础能力
- **多协议 LLM**：支持 Anthropic Claude 和 OpenAI 兼容端点（DeepSeek 等），通过 YAML 配置切换
- **流式输出**：回复逐字实时呈现，支持扩展思考（thinking）
- **多轮上下文**：单会话内完整对话历史，跨轮引用前文

### 工具系统
- **6 个内置工具**：读文件、写文件、改文件、执行命令、按模式找文件、搜代码内容
- **MCP 客户端**：自动发现并注册外部 MCP Server 工具（stdio + Streamable HTTP）
- **Skill 技能包**：可复用的 AI 操作封装成 Markdown，两阶段加载，按需激活
- **子 Agent**：定义式 / Fork 式两种委派，跑到底模式，后台任务管理
- **团队协作**：长期小组、点对点消息、共享任务清单、Coordinator 模式

### 安全与可靠性
- **五层权限**：危险命令黑名单 → 路径沙箱 → 可配置规则 → 权限模式 → 人在回路
- **四档模式**：default / acceptEdits / plan / bypassPermissions，运行时切换
- **上下文管理**：两层压缩（工具结果落盘 + LLM 摘要），长时间工作不撑爆窗口
- **Hook 生命周期**：事件 + 条件 + 动作三要素，工具执行前可拦截
- **Worktree 隔离**：子 Agent 并行干活时用 git worktree 隔离文件修改

### 体验优化
- **slash 命令**：12+ 内置命令 + Tab 补全
- **会话持久化**：JSONL 追加写，`/resume` 恢复历史会话
- **自动记忆**：从对话中自动提取用户偏好、项目知识，跨会话注入

---

## 🚀 快速开始

### 环境要求
- Python 3.12+
- macOS / Linux（Windows 未完整测试）

### 安装

```bash
git clone https://github.com/buyaoxiangcaiduojiaconghua/mi-code-agent.git
cd mi-code-agent

# 创建虚拟环境并安装
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 配置

复制配置模板，填入你的 API Key：

```bash
cp .micodeagent/config.yaml.example .micodeagent/config.yaml
```

编辑 `.micodeagent/config.yaml`：

```yaml
providers:
  - name: "deepseek-chat"
    protocol: "openai"
    model: "deepseek-chat"
    base_url: "https://api.deepseek.com"
    api_key: "sk-你的key"       # 支持 ${VAR} 从环境变量读取
    context_window: 128000       # 可选，未配置时按协议默认
```

> ⚠️ `config.yaml` 已被 `.gitignore` 忽略，不会提交到仓库。

### 启动

```bash
python -m micodeagent
# 或
micodeagent
```

---

## 📖 使用

### slash 命令

| 命令 | 说明 |
|------|------|
| `/help` | 列出所有可用命令 |
| `/status` | 显示运行状态（模式/用量/工具数） |
| `/plan` | 进入计划模式（只读工具） |
| `/do` | 退出计划模式并按计划执行 |
| `/compact` | 手动压缩上下文 |
| `/clear` | 清空当前会话 |
| `/resume` | 恢复历史会话 |
| `/review` | 审查代码变更 |
| `/session` | 显示会话信息 |
| `/memory` | 列出记忆文件 |
| `/permission` | 显示权限模式 |
| `/skill` | 列出可用 Skill |
| `/exit` | 退出 |

### 权限模式切换

按 `Shift+Tab` 循环切换：default → acceptEdits → plan → bypassPermissions

### 多行输入

- `Enter` 提交
- `Alt+Enter` 插入换行

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
├── instructions/   # 项目指令加载（MEWCODE.md）
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

---

## 🧪 开发

### 运行测试

```bash
pytest tests/ -q          # 251 个单元测试
```

### 代码规范

```bash
ruff check src/micodeagent tests
ruff format --check src/micodeagent tests
```

### 技术栈

- **TUI**：[Textual](https://textual.textualize.io/) + Rich
- **LLM SDK**：[anthropic](https://github.com/anthropics/anthropic-sdk-python) / [openai](https://github.com/openai/openai-python)
- **MCP**：[mcp](https://github.com/modelcontextprotocol/python-sdk)
- **配置**：PyYAML

---

## 🗺️ 章节演进

本项目通过 14 个章节（ch02 → ch15）逐步构建，每章对应一个能力维度，完整的设计文档见 [`docs/`](docs/)：

| 章节 | 能力 | 目录 |
|------|------|------|
| ch02 | 纯对话客户端 | `docs/ch02/` |
| ch03 | 工具系统 | `docs/ch03/` |
| ch04 | Agent Loop（ReAct） | `docs/ch04-agent-loop/` |
| ch05 | 系统提示工程化 | `docs/ch05-prompt-engineering/` |
| ch06 | 五层权限系统 | `docs/ch06-permission/` |
| ch07 | MCP 客户端 | `docs/ch07-mcp/` |
| ch08 | 上下文管理 | `docs/ch08/` |
| ch09 | 项目记忆与会话持久化 | `docs/ch09/` |
| ch10 | slash 命令体系 | `docs/ch10/` |
| ch11 | Skill 系统 | `docs/ch11/` |
| ch12 | Hook 系统 | `docs/ch12/` |
| ch13 | 子 Agent | `docs/ch13/` |
| ch14 | Worktree 隔离 | `docs/ch14/` |
| ch15 | Team 协作 | `docs/ch15/` |

---

## 📄 许可证

MIT License
