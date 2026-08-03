# MACF - Multi-Agent Collaboration Framework

多智能体协作框架 - 让多个 LLM 通过消息中间件相互对话、辩论、达成共识，输出结构化方案文档。

## 🏗️ 架构

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: MACF 讨论层（多模型协作）                           │
│                                                              │
│  Agent A (DeepSeek) ←→ Agent B (LongCat/DeepSeek)          │
│         ↓                                                    │
│  辩论、评估、共识                                              │
│         ↓                                                    │
│  输出: final_plan.md                                         │
└─────────────────────────────────────────────────────────────┘
```

## ✨ 特性

- **多模型协作**：不同 Agent 可以用不同 LLM
- **消息驱动**：基于 Redis Pub/Sub，支持跨进程
- **灵活配置**：YAML 配置，随时改角色、模型、工具
- **共识追踪**：自动追踪已达成的共识点
- **共享记忆**：Agent 之间共享上下文，避免重复讨论
- **结构化输出**：根据 scope（backend/frontend/fullstack）生成方案

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 确保 Redis 运行

```bash
redis-cli ping
# 应该返回 PONG
```

### 3. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env 填入你的 API Key
```

### 4. 运行

**单进程模式**（一个终端）：
```bash
python3 run_debate.py
```

**多进程模式**（推荐，3 个终端）：

```bash
# 终端 1
python3 run_agent.py --id agent-a --config config/debate.yaml

# 终端 2
python3 run_agent.py --id agent-b --config config/debate.yaml

# 终端 3
python3 run_orchestrator.py --config config/debate.yaml
```

## 📝 配置

编辑 `config/debate.yaml`：

```yaml
task:
  name: "你的任务名称"
  scope: fullstack  # backend / frontend / fullstack
  description: |
    任务描述...

agents:
  - id: agent-a
    name: "前端架构师"
    model: deepseek
    role: "..."
    workspace: ./workspace/agent-a
    tools: [read_file, list_files]

  - id: agent-b
    name: "后端工程师"
    model: deepseek
    role: "..."
    workspace: ./workspace/agent-b
    tools: [read_file, list_files]
```

## 📁 项目结构

```
macf_demo/
├── config/
│   └── debate.yaml          # 配置文件
├── macf/                    # 框架核心
│   ├── protocol.py          # 消息协议
│   ├── broker.py            # Redis 消息总线
│   ├── agent.py             # Agent 类
│   ├── orchestrator.py      # 协调器
│   ├── tools.py             # 工具集
│   └── shared_memory.py     # 共享记忆
├── workspace/               # 工作区（运行时生成）
│   ├── target/              # 待审查代码
│   └── final_plan.md        # 最终方案
├── run_debate.py            # 单进程模式
├── run_agent.py             # 多进程 - 启动单个 Agent
├── run_orchestrator.py      # 多进程 - 协调器
├── .env.example             # 环境变量示例
└── .gitignore
```

## 🔧 环境变量

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `LONGCAT_API_KEY` | LongCat API Key |

## 📄 License

MIT
