# MACF 完整演示

## 场景：设计一个即时通讯消息系统

### 1. 准备待讨论代码

```python
# workspace/target/message_system.py
# 这是一个有问题的简单实现
```

### 2. 配置辩论

```yaml
# config/debate.yaml
task:
  name: "即时通讯消息系统设计"
  scope: fullstack
  description: |
    设计并优化一个支持单聊 + 群聊的即时通讯消息模块。
    ...

agents:
  - id: agent-a
    name: "前端架构师"
    model: deepseek
    role: "资深前端架构师，擅长 React/Vue、WebSocket..."

  - id: agent-b
    name: "后端工程师"
    model: deepseek
    role: "资深后端工程师，擅长 Python、数据库设计..."
```

### 3. 运行

```bash
redis-cli FLUSHALL

# 终端 1
python3 run_agent.py --id agent-a --config config/debate.yaml

# 终端 2
python3 run_agent.py --id agent-b --config config/debate.yaml

# 终端 3
python3 run_orchestrator.py --config config/debate.yaml
```

### 4. 实时输出

```
============================================================
🎬 Debate 开始
   任务: 即时通讯消息系统设计
   发起者: agent-a
   审查者: agent-b
============================================================

📨 [agent-a] 收到来自 [orchestrator] 的消息 (task_start)
🌐 [agent-a] 调用 LLM (轮次 1)...
✅ [agent-a] LLM 响应完成 (1.9s)
🔧 [agent-a] 调用工具: list_files({})
🔧 [agent-a] 调用工具: read_file({'path': 'message_system.py'})
🌐 [agent-a] 调用 LLM (轮次 2)...
✅ [agent-a] LLM 响应完成 (1.3s)
🔧 [agent-a] 调用工具: read_file({'path': 'user_api.py'})
🌐 [agent-a] 调用 LLM (轮次 3)...
✅ [agent-a] LLM 响应完成 (7.2s)
🔧 [agent-a] 调用工具: send_message({...})
📤 发布消息 → macf:agent:agent-b

📨 [agent-b] 收到来自 [agent-a] 的消息 (proposal)
🌐 [agent-b] 调用 LLM (尝试 1)...
✅ [agent-b] LLM 响应完成 (5.6s)
📤 发布消息 → macf:agent:agent-a (critique)

📨 [agent-a] 收到来自 [agent-b] 的消息 (critique)
🌐 [agent-a] 调用 LLM (尝试 1)...
✅ [agent-a] LLM 响应完成 (5.9s)
📤 发布消息 → macf:agent:agent-b (proposal)

... (多轮讨论)

🎉 达成共识! Agent [agent-b] 表示同意

============================================================
📝 生成最终方案文档 (范围: fullstack)...
============================================================

✅ 最终方案已保存:
   📁 项目: ./workspace/final_plan.md
   🖥️ 桌面: ~/Desktop/macf-final-plan.md

📊 讨论统计:
   - 总消息数: 168
   - 共识点: 84 个
   - 争议点: 0 个

📋 方案预览:
   # 即时通讯消息系统设计 - 技术方案
   ## 1. 需求概述
   ## 2. 核心设计决策
   ## 3. 接口契约
   ## 4. 数据模型
   ## 5. 关键实现细节
   ## 6. 实施步骤
```

### 5. 生成的方案

```markdown
# 即时通讯消息系统设计 - 技术方案

> **生成时间**: 2026-08-03 14:12:42
> **讨论轮次**: 168 条消息
> **达成共识**: 84 个
> **范围**: fullstack
---

## 1. 需求概述
...

## 2. 核心设计决策
1. 消息存储按 conversation_id 分片 [agent-a]
2. 实时推送用 WebSocket [agent-b]
3. 已读状态用会话级游标 [agent-a]
4. 群聊采用读扩散 [agent-b]
5. 分页用游标分页 [agent-a]
6. 在线状态心跳 30s/超时 90s [agent-b]
...

## 3. 接口契约
...

## 4. 数据模型
...

## 5. 关键实现细节
...

## 6. 实施步骤
...
```

### 6. 交给 Claude Code 执行

```bash
claude -p --file ~/Desktop/macf-final-plan.md
```

Claude Code 会按照方案文档逐步实现代码。
