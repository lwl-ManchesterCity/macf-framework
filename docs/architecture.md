# MACF 架构设计文档

## 1. 系统概述

MACF (Multi-Agent Collaboration Framework) 是一个让多个 LLM Agent 通过消息中间件进行协作的框架。

## 2. 核心组件

### 2.1 Protocol (消息协议)

```
Message
├── id: str              # 消息唯一 ID
├── from_agent: str      # 发送者
├── to_agent: str        # 接收者
├── type: MessageType    # 消息类型
├── payload: dict        # 消息内容
├── timestamp: str       # 时间戳
└── reply_to: str        # 回复哪条消息

MessageType (枚举)
├── TASK_START           # 开始任务
├── TASK_COMPLETE        # 任务完成
├── TASK_REVIEW          # 收敛推动
├── PROPOSAL             # 提出方案
├── CRITIQUE             # 批评/质疑
├── REVISION             # 修改方案
├── APPROVAL             # 同意/批准
└── REJECTION            # 驳回
```

### 2.2 Broker (消息总线)

基于 Redis Pub/Sub 实现：

```
Broker
├── redis_client: Redis 连接
├── pubsub: Redis Pub/Sub 实例
├── publish(message)     # 发布消息
├── subscribe(channel)  # 订阅频道
└── start_listener()     # 启动监听线程
```

频道设计：
- `macf:agent:{agent_id}` —— Agent 个人频道
- `macf:broadcast` —— 全局广播频道

### 2.3 Agent (智能体)

```
Agent
├── agent_id: str
├── name: str
├── role: str
├── client: OpenAI 客户端
├── broker: MessageBroker
├── tool_executor: ToolExecutor
├── shared_memory: SharedMemory
├── conversation_history: list
└── _should_exit: bool

核心方法：
├── _on_message()        # 消息回调
├── _generate_reply()    # 生成回复
├── _process_conversation()  # 多轮对话
└── start_task()         # 主动发起任务
```

### 2.4 Orchestrator (协调器)

```
Orchestrator
├── config: dict
├── broker: MessageBroker
├── agents: dict
├── debate_log: list
├── agreed_points: list
└── consensus_reached: bool

核心方法：
├── run_debate()         # 启动辩论
├── _wait_for_completion()   # 等待完成
├── _push_convergence()  # 推动收敛
├── _generate_final_plan()   # 生成方案
└── _shutdown_agents()   # 通知退出
```

### 2.5 SharedMemory (共享记忆)

```
SharedMemory
├── memory_path: str

核心方法：
├── add_agreed_point()      # 添加共识
├── add_disputed_point()    # 添加争议
├── mark_file_read()        # 标记文件已读
├── get_agreed_summary()     # 获取共识摘要
├── get_disputed_summary()   # 获取争议摘要
└── get_full_context()       # 获取完整上下文
```

## 3. 数据流

```
┌──────────────────────────────────────────────────────────┐
│                     启动阶段                               │
│                                                          │
│  1. 加载 config/debate.yaml                              │
│  2. 初始化 Redis 连接                                     │
│  3. 创建 Agent A + Agent B（各自独立的 Redis 连接）        │
│  4. 创建 Orchestrator                                     │
│  5. 所有 Agent 启动监听线程                                │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                     辩论阶段                               │
│                                                          │
│  1. Orchestrator 发送 TASK_START 给 Agent A              │
│  2. Agent A 读取代码 → 生成 PROPOSAL                     │
│  3. Agent B 收到 PROPOSAL → 生成 CRITIQUE                │
│  4. Agent A 收到 CRITIQUE → 生成 REVISION                │
│  5. 循环直到 Agent B 生成 APPROVAL                        │
│  6. 每次消息更新 SharedMemory                            │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                     收尾阶段                               │
│                                                          │
│  1. 检测共识关键词 → consensus_reached = True            │
│  2. 生成 final_plan.md（基于 SharedMemory）              │
│  3. 发送 TASK_COMPLETE 通知所有 Agent                     │
│  4. Agent 退出监听循环                                    │
│  5. 清理 Redis 连接                                      │
└──────────────────────────────────────────────────────────┘
```

## 4. 状态机

```
Agent 状态：
┌─────────────┐
│   IDLE      │ ← 启动后等待消息
└──────┬──────┘
       │ 收到 TASK_START / 对方消息
       ▼
┌─────────────┐
│  PROCESSING │ ← 读取文件、调用 LLM
└──────┬──────┘
       │ 生成回复
       ▼
┌─────────────┐
│  REPLYING   │ ← 发送消息给对方
└──────┬──────┘
       │ 消息发送完成
       ▼
┌─────────────┐
│   IDLE      │ ← 等待下一条消息
└──────┬──────┘
       │ 收到 TASK_COMPLETE
       ▼
┌─────────────┐
│  EXITING    │ ← 清理资源、退出
└─────────────┘
```

## 5. 容错设计

| 故障场景 | 处理策略 |
|---------|---------|
| API 调用失败 | 指数退避重试（1s → 2s → 4s → 最大 30s） |
| 模型未调用工具 | 文本解析 fallback |
| 参数解析失败 | 使用默认值 |
| 对方 Agent 无响应 | 60s 后发送收敛推动 |
| 讨论停滞 | 120s 后强制结束 |
| Redis 断开 | 日志记录，下次调用重连 |

## 6. 扩展点

### 6.1 添加新模型

```yaml
models:
  gpt4:
    api_key: ${OPENAI_API_KEY}
    base_url: https://api.openai.com/v1
    model: gpt-4o
```

### 6.2 添加新工具

在 `tools.py` 的 `get_tool_definitions()` 中添加：

```python
{
    "type": "function",
    "function": {
        "name": "your_tool",
        "description": "工具描述",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "参数说明"}
            },
            "required": ["param1"]
        }
    }
}
```

### 6.3 多 Agent 协作

```yaml
agents:
  - id: agent-a
    name: "前端架构师"
  - id: agent-b
    name: "后端工程师"
  - id: agent-c
    name: "安全专家"
```
