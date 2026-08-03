# 🤖 MACF - Multi-Agent Collaboration Framework

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org)
[![Redis](https://img.shields.io/badge/Redis-5.0+-red.svg)](https://redis.io)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/lwl-ManchesterCity/macf-framework/pulls)

> 让多个 LLM 像真实团队一样协作：辩论、评审、达成共识，输出可执行的技术方案。

[English](#english) | [中文](#中文)

### 📚 文档

| 文档 | 说明 |
|------|------|
| [架构设计](docs/architecture.md) | 系统架构、数据流、状态机 |
| [API 参考](docs/api.md) | 完整 API 接口文档 |
| [使用指南](docs/guide.md) | 快速开始、配置详解、常见问题 |
| [完整演示](docs/demo.md) | 从零开始的完整演示案例 |
| [路线图](ROADMAP.md) | 版本规划与未来方向 |
| [CHANGELOG](CHANGELOG.md) | 版本变更记录 |
| [License](LICENSE) | MIT License |

---

## 中文

### 💡 为什么要用 MACF？

传统的单 Agent 代码审查或设计存在局限：
- **视角单一**：一个 LLM 可能遗漏问题
- **缺乏讨论**：没有辩论就没有深度
- **上下文丢失**：长对话后忘记前面的约定

MACF 让两个（或多个）AI Agent 像真实工程师团队一样协作：
- 前端架构师 ↔ 后端工程师 实时辩论
- 自动追踪已达成的共识
- 输出结构化的可执行方案

### 🏗️ 架构

```
                    ┌─────────────────────────────────────────┐
                    │           Orchestrator (协调器)           │
                    │  • 启动讨论  • 监控进度  • 推动收敛       │
                    └───────┬─────────────────┬───────────────┘
                            │                 │
              ┌─────────────▼──────┐  ┌──────▼─────────────┐
              │   Agent A          │  │   Agent B           │
              │   前端架构师        │  │   后端工程师         │
              │                    │  │                     │
              │  • 读取代码        │  │  • 读取代码          │
              │  • 提出方案        │◄─┤► • 评审方案          │
              │  • 回应评审        │  │  • 提出修订          │
              │  • 确认共识        │  │  • 确认共识          │
              └─────────┬──────────┘  └──────────┬──────────┘
                        │                        │
                        └──────────┬─────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │      共享记忆 (Shared Memory)  │
                    │  • 共识点记录                  │
                    │  • 文件读取追踪                │
                    │  • 讨论进度统计                │
                    └─────────────────────────────┘
```

### ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🎭 **多角色辩论** | 支持配置不同角色的 Agent（前端/后端/安全/架构师） |
| 🧠 **共享记忆** | Agent 之间共享上下文，避免重复讨论已确认的点 |
| 📊 **共识追踪** | 自动提取并记录已达成的技术决策 |
| 🔄 **强制收敛** | 讨论停滞时自动推动，避免无限循环 |
| 📝 **结构化输出** | 根据 scope（backend/frontend/fullstack）生成可执行方案 |
| 🔌 **灵活扩展** | 支持 DeepSeek、LongCat、OpenAI 等多种 LLM |
| 🛡️ **工具沙盒** | Agent 的文件操作限制在工作区内，安全可靠 |

### 🚀 快速开始

#### 1. 环境要求

- Python 3.10+
- Redis 5.0+
- DeepSeek / LongCat API Key

#### 2. 安装

```bash
# 克隆仓库
git clone https://github.com/lwl-ManchesterCity/macf-framework.git
cd macf_demo

# 安装依赖
pip install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env 填入你的 API Key
```

#### 3. 启动 Redis

```bash
redis-server
# 验证
redis-cli ping  # 返回 PONG
```

#### 4. 准备待讨论代码

```bash
# 把代码放到 workspace/target/
cp your_code.py workspace/target/
```

#### 5. 配置 Agent

编辑 `config/debate.yaml`：

```yaml
task:
  name: "你的任务名称"
  scope: fullstack   # backend / frontend / fullstack
  description: |
    详细说明要讨论的内容...

agents:
  - id: agent-a
    name: "前端架构师"
    model: deepseek
    role: "资深前端架构师，擅长 React/Vue、TypeScript..."
    workspace: ./workspace/agent-a
    tools: [read_file, list_files]

  - id: agent-b
    name: "后端工程师"
    model: deepseek
    role: "资深后端工程师，擅长 Python、数据库设计..."
    workspace: ./workspace/agent-b
    tools: [read_file, list_files]

debate:
  max_turns: 6
  consensus_keywords: ["同意", "方案通过", "可以实施", "达成共识"]
```

#### 6. 运行

**单进程模式**（快速测试）：

```bash
python3 run_debate.py
```

**多进程模式**（推荐，更接近生产）：

```bash
# 终端 1 - 启动 Agent A
python3 run_agent.py --id agent-a --config config/debate.yaml

# 终端 2 - 启动 Agent B
python3 run_agent.py --id agent-b --config config/debate.yaml

# 终端 3 - 启动协调器（触发讨论）
python3 run_orchestrator.py --config config/debate.yaml
```

#### 7. 查看结果

讨论结束后，方案会自动保存到：

- **桌面**：`~/Desktop/macf-final-plan.md`
- **项目内**：`workspace/final_plan.md`

### 📋 输出示例

生成的方案包含：

```markdown
# 任务名称 - 技术方案

## 1. 需求概述
## 2. 核心设计决策（自动从讨论中提取）
## 3. 接口契约（API 表格）
## 4. 数据模型（SQL 建表语句）
## 5. 关键实现细节（流程图）
## 6. 实施步骤（有序列表）
```

### 🔧 配置参考

#### 模型配置

```yaml
models:
  deepseek:
    api_key: ${DEEPSEEK_API_KEY}
    base_url: https://api.deepseek.com
    model: deepseek-chat
  longcat:
    api_key: ${LONGCAT_API_KEY}
    base_url: https://api.longcat.chat/openai
    model: LongCat-2.0
```

#### 可用工具

| 工具 | 功能 |
|------|------|
| `read_file` | 读取工作区文件 |
| `list_files` | 列出工作区文件 |
| `search_code` | 正则搜索代码 |
| `write_file` | 写入文件 |
| `run_command` | 执行命令（带安全黑名单） |

### 🛡️ 安全机制

- **路径越界防护**：Agent 无法访问工作区外的文件
- **命令黑名单**：禁止 `rm -rf /`、`chmod 777` 等危险命令
- **API Key 隔离**：通过 `.env` 文件管理，不提交到 Git

### 📊 讨论流程

```
1. Orchestrator 发送任务给 Agent A
2. Agent A 读取代码 → 提出方案 (proposal)
3. Agent B 收到方案 → 评审反馈 (critique)
4. Agent A 回应 → 修订方案 (revision)
5. 循环直到 Agent B 给出 approval
6. Orchestrator 检测共识 → 生成最终方案
7. 通知所有 Agent 退出
```

### 🤝 贡献

欢迎提交 Issue 和 PR！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送分支 (`git push origin feature/amazing-feature`)
5. 开启 Pull Request

### 📄 License

[MIT](LICENSE) © 2024 lwl-ManchesterCity

---

## English

### 💡 Why MACF?

Traditional single-agent code review has limitations:
- **Single perspective**: One LLM may miss issues
- **No debate**: No discussion means no depth
- **Context loss**: Forget earlier agreements in long conversations

MACF makes two (or more) AI Agents collaborate like a real engineering team:
- Frontend Architect ↔ Backend Engineer debate in real-time
- Auto-tracking of reached consensus
- Output structured, actionable technical proposals

### 🏗️ Architecture

```
                    ┌─────────────────────────────────────────┐
                    │           Orchestrator                   │
                    │  • Start debate  • Monitor  • Converge   │
                    └───────┬─────────────────┬───────────────┘
                            │                 │
              ┌─────────────▼──────┐  ┌──────▼─────────────┐
              │   Agent A          │  │   Agent B           │
              │   Frontend Arch.   │  │   Backend Eng.      │
              │                    │  │                     │
              │  • Read code       │◄─┤► • Review proposal   │
              │  • Propose         │  │  • Revise           │
              │  • Confirm         │  │  • Confirm          │
              └─────────┬──────────┘  └──────────┬──────────┘
                        │                        │
                        └──────────┬─────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │       Shared Memory          │
                    │  • Consensus tracking        │
                    │  • File read history         │
                    │  • Progress stats            │
                    └─────────────────────────────┘
```

### ✨ Features

| Feature | Description |
|---------|-------------|
| 🎭 **Multi-role Debate** | Configure different agent roles |
| 🧠 **Shared Memory** | Agents share context, avoid repetition |
| 📊 **Consensus Tracking** | Auto-extract technical decisions |
| 🔄 **Forced Convergence** | Auto-push when debate stalls |
| 📝 **Structured Output** | Generate proposals by scope |
| 🔌 **Flexible Models** | DeepSeek, LongCat, OpenAI, etc. |
| 🛡️ **Tool Sandbox** | File operations restricted to workspace |

### 🚀 Quick Start

```bash
# Clone
git clone https://github.com/lwl-ManchesterCity/macf-framework.git
cd macf_demo

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API Keys

# Run (single process)
python3 run_debate.py

# Run (multi-process, recommended)
# Terminal 1
python3 run_agent.py --id agent-a --config config/debate.yaml
# Terminal 2
python3 run_agent.py --id agent-b --config config/debate.yaml
# Terminal 3
python3 run_orchestrator.py --config config/debate.yaml
```

### 📄 License

[MIT](LICENSE) © 2024 lwl-ManchesterCity
