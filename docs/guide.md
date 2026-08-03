# 使用指南

## 目录

1. [快速开始](#快速开始)
2. [配置详解](#配置详解)
3. [运行模式](#运行模式)
4. [输出解读](#输出解读)
5. [常见问题](#常见问题)

## 快速开始

### 1. 环境准备

```bash
# 安装 Redis（macOS）
brew install redis
brew services start redis

# 验证
redis-cli ping  # PONG
```

### 2. 安装 MACF

```bash
git clone https://github.com/lwl-ManchesterCity/macf-framework.git
cd macf_demo
pip install -r requirements.txt
```

### 3. 配置

```bash
cp .env.example .env
# 编辑 .env 填入 API Key
```

### 4. 运行

```bash
python3 run_debate.py
```

## 配置详解

### task 配置

```yaml
task:
  name: "My Task"           # 任务名称
  scope: fullstack          # 生成范围：backend / frontend / fullstack
  description: |            # 任务描述（Agent 会读取这段文字）
    详细说明...
```

### agents 配置

```yaml
agents:
  - id: agent-a                      # Agent 唯一 ID
    name: "前端架构师"                # 显示名称
    model: deepseek                   # 使用的模型（对应 models 下的 key）
    role: "详细描述角色职责..."        # 系统提示词
    workspace: ./workspace/agent-a    # 工作区路径
    tools: [read_file, list_files]    # 可用工具
```

### models 配置

```yaml
models:
  deepseek:
    api_key: ${DEEPSEEK_API_KEY}      # 支持环境变量
    base_url: https://api.deepseek.com
    model: deepseek-chat
```

支持的模型：
- DeepSeek (`deepseek-chat`, `deepseek-coder`)
- LongCat (`LongCat-2.0`)
- OpenAI 兼容 API（GPT-4、Claude 等）

## 运行模式

### 单进程模式

适用于快速测试，所有 Agent 在一个进程内运行：

```bash
python3 run_debate.py
```

### 多进程模式

推荐用于生产，每个 Agent 独立进程：

```bash
# 终端 1
python3 run_agent.py --id agent-a --config config/debate.yaml

# 终端 2
python3 run_agent.py --id agent-b --config config/debate.yaml

# 终端 3
python3 run_orchestrator.py --config config/debate.yaml
```

## 输出解读

### final_plan.md

生成的方案文档结构：

```
# 任务名称 - 技术方案

## 1. 需求概述
## 2. 核心设计决策（从讨论中提取）
## 3. 接口契约（API 表格）
## 4. 数据模型（SQL 建表语句）
## 5. 关键实现细节（流程图）
## 6. 实施步骤（有序列表）
```

### shared_memory.json

共享记忆文件，记录：

```json
{
  "agreed_points": [...],    // 已达成的共识
  "disputed_points": [...],  // 待解决的争议
  "files_read": {...},       // 文件读取记录
  "message_count": 123,      // 总消息数
  "last_update": "..."       // 最后更新时间
}
```

### debate_log.json

完整讨论记录，用于审计和回放。

## 常见问题

### Q: Agent 没有响应？

检查：
1. Redis 是否运行：`redis-cli ping`
2. API Key 是否正确：检查 `.env` 文件
3. 模型余额是否充足

### Q: 讨论陷入循环？

框架内置强制收敛机制：
- 60s 无新消息 → 发送推动消息
- 120s 无响应 → 强制结束
- 达到 `max_turns * 3` 轮 → 强制结束

### Q: 如何自定义 Agent 角色？

修改 `config/debate.yaml` 中的 `role` 字段：

```yaml
agents:
  - id: agent-a
    name: "安全专家"
    role: "你是一位资深安全专家，擅长 OWASP、渗透测试、代码审计..."
```

### Q: 支持哪些 LLM？

任何兼容 OpenAI API 的模型：
- DeepSeek
- LongCat
- GPT-4 / GPT-4o
- Claude（通过 OpenAI 兼容接口）
- 本地模型（Ollama、vLLM 等）
