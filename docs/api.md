# MACF API 参考

## Protocol

### Message

| 字段 | 类型 | 说明 |
|------|------|------|
| id | str | 消息唯一 ID，格式 `msg-{hex8}` |
| from_agent | str | 发送者 Agent ID |
| to_agent | str | 接收者 Agent ID |
| type | MessageType | 消息类型 |
| payload | dict | 消息内容 |
| timestamp | str | ISO 8601 时间戳 |
| reply_to | str | 可选，回复哪条消息 |

### MessageType

| 值 | 说明 |
|------|------|
| task_start | 开始任务 |
| task_complete | 任务完成 |
| task_review | 收敛推动 |
| proposal | 提出方案 |
| critique | 批评/质疑 |
| revision | 修改方案 |
| approval | 同意/批准 |
| rejection | 驳回 |

## Broker

```python
class MessageBroker:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0)
    def publish(self, message: Message) -> bool
    def subscribe(self, agent_id: str, handler: Callable)
    def subscribe_pattern(self, pattern: str, handler: Callable)
    def start_listener(self)
    def stop_listener(self)
    def close(self)
```

## Agent

```python
class Agent:
    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str,
        model_config: dict,
        workspace: str,
        tools: list,
        broker: MessageBroker,
        max_tool_rounds: int = 5,
    )
    def start_task(self, task_description: str, to_agent: str = "agent-b")
    def send_direct_message(self, to_agent: str, content: str, msg_type: MessageType)
    def cleanup(self)
```

## Orchestrator

```python
class DebateOrchestrator:
    def __init__(self, config: dict)
    def run_debate(self, task: str, starter: str = "agent-a", responder: str = "agent-b")
    def cleanup(self)
```

## SharedMemory

```python
class SharedMemory:
    def __init__(self, memory_path: str = "./workspace/shared_memory.json")
    def add_agreed_point(self, point: str, agreed_by: str = None)
    def add_disputed_point(self, point: str, reason: str = None)
    def mark_file_read(self, filename: str, read_by: str)
    def increment_message_count(self)
    def get_agreed_summary(self) -> str
    def get_disputed_summary(self) -> str
    def get_files_read_summary(self) -> str
    def get_full_context(self) -> str
    def get_stats(self) -> dict
```

## Tools

| 工具 | 说明 | 参数 |
|------|------|------|
| read_file | 读取文件 | path: str |
| write_file | 写入文件 | path: str, content: str |
| list_files | 列出文件 | - |
| search_code | 正则搜索 | pattern: str, file_type: str |
| run_command | 执行命令 | command: str |

## 配置参考

```yaml
task:
  name: "任务名称"
  scope: fullstack  # backend / frontend / fullstack
  description: |
    任务描述...

broker:
  host: localhost
  port: 6379

models:
  model_name:
    api_key: ${ENV_VAR}
    base_url: https://api.example.com
    model: model-name

agents:
  - id: agent-a
    name: "角色名称"
    model: model_name
    role: "角色描述..."
    workspace: ./workspace/agent-a
    tools: [read_file, list_files]

debate:
  max_turns: 6
  consensus_keywords: ["同意", "方案通过", "可以实施", "达成共识"]
```
