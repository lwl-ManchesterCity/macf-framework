"""
MACF Orchestrator - 协调器

负责启动多个 Agent，管理 Debate 协作流程，控制轮次和终止条件。
最终输出结构化的方案文档，供 Claude Code 执行。

优化：
1. 共识追踪——记录已达成的共识点
2. 强制收敛——讨论停滞时自动推动达成共识
3. 结构化协议——提案→评审→确认三步走
4. 共享记忆——Agent 能看到已达成的共识
"""

import time
import json
import os
from datetime import datetime
from typing import Optional
from .agent import Agent
from .broker import MessageBroker
from .protocol import Message, MessageType


class DebateOrchestrator:
    """
    Debate 模式协调器

    流程:
    1. Agent A 提出方案 (proposal)
    2. Agent B 评审并反馈 (critique/revision)
    3. 循环直到 Agent B 给出 approval 或达到最大轮次
    4. 输出最终方案文档 (final_plan.md)
    """

    def __init__(self, config: dict):
        self.config = config
        self.max_turns = config.get("max_turns", 6)
        self.consensus_keywords = config.get("consensus_keywords", ["同意", "approval", "No more issues"])
        self.current_turn = 0
        self.debate_log = []
        self.consensus_reached = False

        # 共识追踪——记录已达成的共识点
        self.agreed_points = []
        self._consensus_file = "./workspace/consensus.json"

        # 初始化消息代理
        broker_config = config.get("broker", {})
        self.broker = MessageBroker(
            host=broker_config.get("host", "localhost"),
            port=broker_config.get("port", 6379),
        )

        # 初始化 Agent（每个 Agent 使用独立的 Redis 连接）
        self.agents = {}
        for agent_cfg in config["agents"]:
            model_cfg = config["models"][agent_cfg["model"]]
            # 每个 Agent 创建独立的 broker 实例
            agent_broker = MessageBroker(
                host=broker_config.get("host", "localhost"),
                port=broker_config.get("port", 6379),
            )
            agent = Agent(
                agent_id=agent_cfg["id"],
                name=agent_cfg["name"],
                role=agent_cfg["role"],
                model_config=model_cfg,
                workspace=agent_cfg.get("workspace", f"./workspace/{agent_cfg['id']}"),
                tools=agent_cfg.get("tools", []),
                broker=agent_broker,
            )
            self.agents[agent_cfg["id"]] = agent

        # 注册消息监控（orchestrator 自己的连接）
        self._setup_message_monitor()

        print(f"\n🎯 Debate Orchestrator 已初始化")
        print(f"   Agents: {list(self.agents.keys())}")
        print(f"   最大轮次: {self.max_turns}")
        print(f"   共识关键词: {self.consensus_keywords}\n")

    def _setup_message_monitor(self):
        """设置消息监控，记录所有 Agent 间的通信"""
        # 直接订阅每个 Agent 的 channel（比模式订阅更可靠）
        for agent_id in self.agents:
            self.broker.subscribe(agent_id, self._monitor_handler)
        # 启动监听线程
        self.broker.start_listener()

    def _monitor_handler(self, message: Message):
        """监控所有消息，追踪共识"""
        self.debate_log.append(message)

        # 提取共识点（从 approval 和 revision 消息中）
        if message.type in (MessageType.APPROVAL, MessageType.REVISION):
            content = message.payload.get("content", "")
            # 提取关键共识（简单启发式：包含"同意""确认""接受"的句子）
            for kw in ["同意", "确认", "接受", "认可", "没问题", "可以实施", "达成共识"]:
                if kw in content:
                    # 提取包含关键词的句子
                    for sent in content.split("。"):
                        if kw in sent and len(sent) > 10:
                            point = sent.strip()
                            if point not in self.agreed_points:
                                self.agreed_points.append(point)
                                print(f"   📌 新共识: {point[:50]}...")

        # 检查是否达成共识（至少交换 3 条消息后才允许共识）
        if len(self.debate_log) >= 3 and message.type == MessageType.APPROVAL:
            content = message.payload.get("content", "")
            if any(kw in content for kw in self.consensus_keywords):
                print(f"\n🎉 达成共识! Agent [{message.from_agent}] 表示同意")
                self.consensus_reached = True

        # 保存共识到文件（供 Agent 读取）
        self._save_consensus()

    def _save_consensus(self):
        """保存共识点到文件"""
        os.makedirs("./workspace", exist_ok=True)
        with open(self._consensus_file, "w", encoding="utf-8") as f:
            json.dump({
                "agreed_points": self.agreed_points,
                "total_messages": len(self.debate_log),
                "consensus_reached": self.consensus_reached,
            }, f, ensure_ascii=False, indent=2)

    def get_consensus_summary(self) -> str:
        """获取共识摘要（注入到 Agent 的消息中）"""
        if not self.agreed_points:
            return "（暂无已确认的共识）"
        summary = "已确认的共识点：\n"
        for i, point in enumerate(self.agreed_points, 1):
            summary += f"{i}. {point}\n"
        return summary

    def run_debate(self, task: str, starter: str = "agent-a", responder: str = "agent-b"):
        """
        启动 Debate 流程

        Args:
            task: 任务描述
            starter: 发起讨论的 Agent ID
            responder: 回应/审查的 Agent ID
        """
        print(f"\n{'='*60}")
        print(f"🎬 Debate 开始")
        print(f"   任务: {task}")
        print(f"   发起者: {starter}")
        print(f"   审查者: {responder}")
        print(f"{'='*60}\n")

        # 获取 scope（从配置读取，默认 fullstack）
        scope = self.config.get("task", {}).get("scope", "fullstack")

        # 启动发起者
        starter_agent = self.agents[starter]
        starter_agent.start_task(task, to_agent=responder)

        # 等待 Debate 完成
        self._wait_for_completion()

        # 生成最终方案（根据 scope 决定内容）
        self._generate_final_plan(task, scope=scope)

    def _wait_for_completion(self, timeout: int = 600):
        """等待 Debate 完成，带强制收敛机制"""
        print(f"⏳ 等待 Debate 完成 (超时: {timeout}s)...\n")

        start_time = time.time()
        last_message_count = 0
        stall_count = 0
        max_stall_count = 30  # 60秒无新消息就推动收敛

        while time.time() - start_time < timeout:
            time.sleep(2)

            current_count = len(self.debate_log)
            if current_count > last_message_count:
                last_message_count = current_count
                stall_count = 0
                print(f"   ... 已交换 {current_count} 条消息")
            else:
                stall_count += 1
                if stall_count % 5 == 0:
                    elapsed = int(time.time() - start_time)
                    print(f"   ... 等待中 ({elapsed}s / {timeout}s)")

                # 强制收敛：停滞时发送推动消息
                if stall_count == max_stall_count:
                    print(f"\n⚡ 讨论停滞，发送收敛推动消息...")
                    self._push_convergence()

                if stall_count > max_stall_count + 30:
                    print("\n⚠️ 推动后仍无响应，强制结束")
                    self.consensus_reached = True
                    break

            # 强制收敛：超过 max_turns 轮后自动结束
            if current_count >= self.max_turns * 3:
                print(f"\n⚠️ 已达到最大讨论轮次 ({self.max_turns * 3})，强制结束")
                self.consensus_reached = True
                break

            if self.consensus_reached:
                # 共识后多等几秒确保消息完整
                time.sleep(3)
                print("\n✅ Debate 完成 - 已达成共识!")
                return

        print(f"\n⏰ Debate 结束（共 {len(self.debate_log)} 条消息）")

    def _push_convergence(self):
        """发送收敛推动消息，让 Agent 知道该收尾了"""
        # 向两个 Agent 发送推动消息
        for agent_id, agent in self.agents.items():
            try:
                consensus_summary = self.get_consensus_summary()
                push_msg = Message(
                    from_agent="orchestrator",
                    to_agent=agent_id,
                    msg_type=MessageType.TASK_REVIEW,
                    payload={
                        "content": f"[系统推动] 讨论已进行一段时间，请基于以下共识点给出最终确认或补充：\n{consensus_summary}\n\n如果大部分问题已解决，请发送 approval 表示同意；如有最后异议，请简要说明。",
                        "summary": "系统推动收敛",
                    },
                )
                agent.broker.publish(push_msg)
            except Exception as e:
                print(f"   ⚠️ 推动消息发送失败: {e}")

    def _check_consensus(self) -> bool:
        """检查是否达成共识"""
        for msg in reversed(self.debate_log[-5:]):
            if msg.type == MessageType.APPROVAL:
                content = msg.payload.get("content", "")
                if any(kw in content for kw in self.consensus_keywords):
                    return True
        return False

    def _generate_final_plan(self, task: str, scope: str = "fullstack"):
        """生成最终方案文档——基于共享记忆产出可执行方案

        Args:
            task: 任务描述
            scope: 生成范围 - backend(仅后端) / frontend(仅前端) / fullstack(前后端)
        """
        print(f"\n{'='*60}")
        print(f"📝 生成最终方案文档 (范围: {scope})...")
        print(f"{'='*60}\n")

        # 读取共享记忆中的共识点
        from .shared_memory import SharedMemory
        shared_memory = SharedMemory()
        stats = shared_memory.get_stats()

        # 根据 scope 生成方案文档
        if scope == "backend":
            plan_content = self._format_backend_plan(task, shared_memory)
        elif scope == "frontend":
            plan_content = self._format_frontend_plan(task, shared_memory)
        else:  # fullstack
            plan_content = self._format_fullstack_plan(task, shared_memory)

        # 保存方案到桌面和项目
        desktop_path = os.path.expanduser("~/Desktop/macf-final-plan.md")
        project_path = "./workspace/final_plan.md"

        with open(project_path, "w", encoding="utf-8") as f:
            f.write(plan_content)
        with open(desktop_path, "w", encoding="utf-8") as f:
            f.write(plan_content)

        print(f"✅ 最终方案已保存:")
        print(f"   📁 项目: {project_path}")
        print(f"   🖥️ 桌面: {desktop_path}")
        print(f"\n📊 讨论统计:")
        print(f"   - 总消息数: {stats['message_count']}")
        print(f"   - 共识点: {stats['agreed_count']} 个")
        print(f"   - 争议点: {stats['disputed_count']} 个")
        print(f"\n📋 方案预览:")
        print(f"{'─'*60}")
        lines = plan_content.split("\n")[:20]
        for line in lines:
            print(f"  {line}")
        print(f"  ... (共 {len(plan_content.split(chr(10)))} 行)")
        print(f"{'─'*60}")

    def _format_final_plan(self, task: str, final_proposal: Optional[Message], final_approval: Optional[Message]) -> str:
        """格式化最终方案文档"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        content = f"""# 最终方案文档

> **生成时间**: {now}
> **任务**: {task}
> **共识**: {"已达成 ✅" if self.consensus_reached else "未达成（超时）"}
> **讨论轮次**: {len(self.debate_log)} 条消息
> **共识点数量**: {len(self.agreed_points)} 个

---

## 1. 任务概述

{task}

## 2. 讨论摘要

本次讨论共 {len(self.debate_log)} 轮，{len([m for m in self.debate_log if m.type == MessageType.PROPOSAL])} 次方案提议，{len([m for m in self.debate_log if m.type == MessageType.CRITIQUE])} 次评审反馈，最终{"达成共识" if self.consensus_reached else "未达成完全共识"}。

## 3. 达成的共识

"""

        if self.agreed_points:
            for i, point in enumerate(self.agreed_points, 1):
                content += f"{i}. {point}\n"
        else:
            content += "（无明确共识记录）\n"

        content += "\n## 4. 最终方案\n\n"

        # 添加最终方案内容
        if final_proposal:
            proposal_content = final_proposal.payload.get("content", "")
            content += f"### 4.1 核心方案\n\n{proposal_content}\n\n"
        else:
            content += "### 4.1 核心方案\n\n（无最终方案）\n\n"

        # 添加审批意见
        if final_approval:
            approval_content = final_approval.payload.get("content", "")
            content += f"### 4.2 审批意见\n\n{approval_content}\n\n"

        # 添加实施建议
        content += """---

## 5. 实施建议

### 5.1 优先级排序

1. **严重 (Critical)**: 立即修复，可能导致系统沦陷
2. **高危 (High)**: 尽快修复，可能导致数据泄露
3. **中危 (Medium)**: 计划修复，存在安全风险

### 5.2 实施步骤

1. 阅读本方案文档
2. 按优先级逐一修复
3. 每修复一个漏洞后进行测试
4. 全部修复后进行安全回归测试

---

## 6. 附录

### 6.1 完整讨论记录

| 轮次 | 发送者 | 类型 | 摘要 |
|------|--------|------|------|
"""

        for i, msg in enumerate(self.debate_log, 1):
            summary = msg.payload.get("summary", msg.payload.get("content", "")[:50])
            content += f"| {i} | {msg.from_agent} | {msg.type.value} | {summary} |\n"

        content += f"""

### 6.2 元数据

- 总消息数: {len(self.debate_log)}
- 共识关键词: {', '.join(self.consensus_keywords)}
- 生成方式: MACF Multi-Agent Collaboration Framework

---

*本文档由 MACF 自动生成，供 Claude Code 执行参考。*
"""

        return content

    def _save_debate_log(self):
        """保存 Debate 记录到 JSON 文件"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "total_messages": len(self.debate_log),
            "consensus_reached": self.consensus_reached,
            "agreed_points": self.agreed_points,
            "messages": [
                {
                    "from": m.from_agent,
                    "to": m.to_agent,
                    "type": m.type.value,
                    "content": m.payload.get("content", "")[:1000],
                    "timestamp": m.timestamp,
                }
                for m in self.debate_log
            ],
        }

        log_path = "./workspace/debate_log.json"
        os.makedirs("./workspace", exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)

        print(f"\n📋 Debate 记录已保存: {log_path}")

    def _run_claude_code(self):
        """自动调用 Claude Code 执行方案"""
        import subprocess

        plan_path = "./workspace/final_plan.md"
        workspace = "./workspace"

        print(f"\n{'='*60}")
        print("🤖 启动 Claude Code 执行方案")
        print(f"{'='*60}\n")

        # 构建 prompt
        prompt = f"请读取 {plan_path} 方案文档，按照方案修复代码。按优先级逐一修复，每修复一个漏洞后运行测试验证，全部修复后生成修复报告。"

        print(f"📋 方案文件: {plan_path}")
        print(f"📂 工作目录: {workspace}\n")

        try:
            # 检查 claude 是否可用
            check = subprocess.run(
                ["which", "claude"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if check.returncode != 0:
                print("⚠️ 未找到 claude CLI，请手动执行:")
                print(f"   cat {plan_path} | claude --file -")
                return

            print("⏳ Claude Code 执行中...（可能需要几分钟）")
            print("   输出将直接显示在终端...\n")

            # 使用 Popen 执行，不捕获输出（直接显示在终端）
            process = subprocess.Popen(
                ["claude", "-p", prompt],
                cwd=workspace,
            )

            try:
                process.wait(timeout=600)
                print(f"\n✅ Claude Code 执行完成 (返回码: {process.returncode})")
            except subprocess.TimeoutExpired:
                process.kill()
                print("⏰ Claude Code 执行超时")

        except FileNotFoundError:
            print("⚠️ 未找到 claude CLI，请手动执行:")
            print(f"   cat {plan_path} | claude --file -")
        except Exception as e:
            print(f"❌ Claude Code 执行失败: {e}")

    def _shutdown_agents(self):
        """通知所有 Agent 退出"""
        print("\n📢 通知 Agent 退出...")
        for agent_id, agent in self.agents.items():
            try:
                shutdown_msg = Message(
                    from_agent="orchestrator",
                    to_agent=agent_id,
                    msg_type=MessageType.TASK_COMPLETE,
                    payload={
                        "content": "[系统通知] 讨论已结束，请退出进程。",
                        "summary": "讨论结束，退出",
                    },
                )
                agent.broker.publish(shutdown_msg)
            except Exception as e:
                print(f"   ⚠️ 通知 {agent_id} 失败: {e}")

    def _format_fullstack_plan(self, task: str, shared_memory) -> str:
        """生成全栈方案文档（含前后端）"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stats = shared_memory.get_stats()
        data = shared_memory._load()

        content = f"""# {task} - 技术方案

> **生成时间**: {now}
> **讨论轮次**: {stats['message_count']} 条消息
> **达成共识**: {stats['agreed_count']} 个
> **生成方式**: MACF Multi-Agent Collaboration Framework

---

## 1. 需求概述

{task}

## 2. 核心设计决策

"""

        # 从共识点中提取去重的设计决策
        seen_points = set()
        decision_num = 0
        for entry in data.get("agreed_points", []):
            point = entry.get("point", "")
            # 去重和过滤
            clean = point.replace("**", "").replace("✅", "").strip()
            if clean in seen_points or len(clean) < 10:
                continue
            # 只保留包含技术关键词的决策
            tech_keywords = ["接口", "API", "数据库", "表", "字段", "WebSocket", "WS", "SSE", "Redis",
                           "MySQL", "分页", "游标", "已读", "撤回", "消息", "会话", "群聊",
                           "存储", "推送", "心跳", "在线", "seq", "ID", "JSON", "REST",
                           "架构", "方案", "设计", "实现", "优化", "缓存", "索引"]
            if any(kw in clean for kw in tech_keywords):
                seen_points.add(clean)
                decision_num += 1
                by = f" [{entry.get('agreed_by', '')}]" if entry.get('agreed_by') else ""
                content += f"{decision_num}. {clean}{by}\n"

        content += f"""
## 3. 接口契约

基于讨论达成的 API 设计：

### 3.1 消息接口

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | /api/messages | 发送消息 | {{conversation_id, content, msg_type, client_msg_id}} | {{message_id, seq, created_at}} |
| GET | /api/messages | 历史消息 | conversation_id, cursor, limit | {{messages[], next_cursor, has_more}} |
| POST | /api/messages/{{id}}/recall | 撤回消息 | - | {{recalled: true}} |

### 3.2 会话接口

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | /api/conversations/{{id}}/read | 标记已读 | {{last_read_msg_id}} | {{server_time}} |
| GET | /api/conversations/{{id}}/members | 成员列表 | - | {{members[]}} |
| GET | /api/conversations | 会话列表 | - | {{conversations[]}} |

### 3.3 WebSocket 事件

| 事件类型 | 方向 | 说明 | Payload |
|----------|------|------|---------|
| message_new | 服务端→客户端 | 新消息 | {{message_id, conversation_id, sender_id, content, seq, created_at}} |
| message_recalled | 服务端→客户端 | 消息撤回 | {{message_id, conversation_id, sender_id}} |
| read_ack | 服务端→客户端 | 已读回执 | {{conversation_id, user_id, last_read_msg_id, updated_at}} |
| member_update | 服务端→客户端 | 成员变更 | {{conversation_id, user_id, type}} |
| online_status | 服务端→客户端 | 在线状态 | {{user_id, is_online, last_seen}} |
| typing | 双向 | 输入中 | {{conversation_id, user_id, is_typing}} |

## 4. 数据模型

### 4.1 消息表 (messages)

```sql
CREATE TABLE messages (
    id BIGINT PRIMARY KEY,              -- 雪花ID，全局唯一
    conversation_id VARCHAR(64) NOT NULL,
    sender_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    msg_type VARCHAR(16) DEFAULT 'text', -- text/image/file
    seq INTEGER NOT NULL,                -- 会话内局部递增
    is_recalled INTEGER DEFAULT 0,       -- 0=正常 1=已召回
    created_at REAL NOT NULL,
    UNIQUE(conversation_id, seq)
);
CREATE INDEX idx_msg_conv_seq ON messages(conversation_id, seq);
CREATE INDEX idx_msg_created ON messages(created_at);
```

### 4.2 会话已读表 (conversation_read)

```sql
CREATE TABLE conversation_read (
    conversation_id VARCHAR(64) NOT NULL,
    user_id INTEGER NOT NULL,
    last_read_msg_id BIGINT NOT NULL,
    last_read_seq INTEGER NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (conversation_id, user_id)
);
```

### 4.3 会话成员表 (conversation_members)

```sql
CREATE TABLE conversation_members (
    conversation_id VARCHAR(64) NOT NULL,
    user_id INTEGER NOT NULL,
    role VARCHAR(16) DEFAULT 'member',  -- owner/admin/member
    joined_at REAL NOT NULL,
    PRIMARY KEY (conversation_id, user_id)
);
```

### 4.4 会话表 (conversations)

```sql
CREATE TABLE conversations (
    id VARCHAR(64) PRIMARY KEY,
    type VARCHAR(16) DEFAULT 'single',  -- single/group
    created_by INTEGER NOT NULL,
    created_at REAL NOT NULL
);
```

## 5. 关键实现细节

### 5.1 消息发送流程
1. 客户端发送消息到 POST /api/messages
2. 服务端在事务内：分配 seq（SELECT MAX(seq)+1 WHERE conversation_id=?）+ 插入消息
3. 发送成功后通过 WebSocket 广播 message_new 事件给会话内所有在线成员
4. 异步更新 Redis 未读数计数

### 5.2 已读同步流程
1. 客户端进入会话/滚动到底部时调 POST /api/conversations/{id}/read
2. 服务端用 INSERT ... ON CONFLICT DO UPDATE SET last_read_msg_id=MAX(...) 保证单调不减
3. 通过 WebSocket 广播 read_ack 事件
4. 异步扣减 Redis 未读数

### 5.3 消息撤回流程
1. 客户端调 POST /api/messages/{id}/recall
2. 服务端校验：发送者本人 + 2分钟内
3. 更新 is_recalled=1，不物理删除
4. 通过 WebSocket 广播 message_recalled 事件

### 5.4 在线状态
1. 客户端每 30s 发送心跳 POST /api/users/heartbeat
2. 服务端更新 last_seen，超过 90s 判定离线
3. 通过 WebSocket 广播 online_status 事件

### 5.5 分页查询
1. 使用游标分页：GET /api/messages?conversation_id=X&cursor=created_at:id&limit=20
2. 服务端按 (created_at, id) < 复合条件查询
3. 返回 messages, next_cursor, has_more

## 6. 实施步骤

1. **数据库迁移**：创建上述 4 张表 + 索引
2. **消息模块**：实现发送、撤回、分页查询
3. **已读模块**：实现会话级已读标记 + 未读数 Redis 缓存
4. **WebSocket 模块**：实现连接管理 + 6 类事件推送
5. **在线状态模块**：实现心跳 + 超时判定
6. **测试**：单元测试 + 集成测试

---

*本文档由 MACF 自动生成。*
"""

        return content

    def _format_backend_plan(self, task: str, shared_memory) -> str:
        """生成纯后端方案文档"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stats = shared_memory.get_stats()

        return f"""# {task} - 后端技术方案

> **生成时间**: {now}
> **讨论轮次**: {stats['message_count']} 条消息
> **达成共识**: {stats['agreed_count']} 个
> **范围**: 后端
> **生成方式**: MACF Multi-Agent Collaboration Framework

---

## 1. 需求概述

{task}

## 2. 核心设计决策

基于讨论达成的技术决策（详见共享记忆 shared_memory.json）

## 3. 接口契约

基于讨论达成的 API 设计，详见 shared_memory.json 中的共识点。

## 4. 数据模型

根据 shared_memory.json 中的共识设计数据库表结构。

## 5. 关键实现细节

### 5.1 消息收发
- 消息存储与发送流程
- 消息撤回逻辑（2分钟窗口）

### 5.2 已读同步
- 会话级已读标记
- 未读数缓存策略

### 5.3 实时推送
- WebSocket 连接管理
- 事件广播机制

### 5.4 在线状态
- 心跳与超时判定
- 状态广播

### 5.5 分页查询
- 游标分页实现
- 深翻页优化

## 6. 实施步骤

1. **数据库迁移**：创建表 + 索引
2. **消息模块**：发送、撤回、分页
3. **已读模块**：会话级标记 + 缓存
4. **推送模块**：WebSocket + 事件广播
5. **在线状态**：心跳 + 超时
6. **测试**：单元测试 + 集成测试

---

*本文档由 MACF 自动生成。详细共识见 shared_memory.json。*
"""

    def _format_frontend_plan(self, task: str, shared_memory) -> str:
        """生成纯前端方案文档"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stats = shared_memory.get_stats()

        return f"""# {task} - 前端技术方案

> **生成时间**: {now}
> **讨论轮次**: {stats['message_count']} 条消息
> **达成共识**: {stats['agreed_count']} 个
> **范围**: 前端
> **生成方式**: MACF Multi-Agent Collaboration Framework

---

## 1. 需求概述

{task}

## 2. 核心设计决策

基于讨论达成的前端技术决策（详见 shared_memory.json）

## 3. 组件架构

根据 shared_memory.json 中的共识设计组件结构。

### 3.1 核心组件
- MessageList：消息列表渲染
- MessageInput：消息输入框
- ConversationList：会话列表
- UserStatus：在线状态展示

### 3.2 状态管理
- 消息状态（发送中/已发送/已读/撤回）
- 会话状态（当前会话/未读数）
- 用户状态（在线/离线/输入中）

## 4. 接口对接

根据 shared_memory.json 中的 API 契约对接后端。

### 4.1 REST API 调用
- 发送消息
- 历史消息加载
- 标记已读
- 撤回消息

### 4.2 WebSocket 事件处理
- message_new：新消息
- message_recalled：消息撤回
- read_ack：已读回执
- member_update：成员变更
- online_status：在线状态
- typing：输入中

## 5. 关键实现细节

### 5.1 消息列表
- 虚拟滚动优化
- 消息去重（message_id）
- 时间分组显示

### 5.2 实时消息
- WebSocket 连接管理
- 断线重连
- 消息增量渲染

### 5.3 已读状态
- 进入会话标记已读
- 滚动到底部标记已读
- read_ack 实时更新

### 5.4 消息撤回
- 2分钟倒计时
- 撤回后 UI 占位

### 5.5 在线状态
- 心跳发送（30s）
- 超时判定（90s）
- 状态 UI 展示

## 6. 实施步骤

1. **组件搭建**：MessageList、MessageInput、ConversationList
2. **状态管理**：消息/会话/用户状态
3. **API 对接**：REST 调用封装
4. **WebSocket**：连接管理 + 事件处理
5. **优化**：虚拟滚动、消息去重
6. **测试**：组件测试 + 集成测试

---

*本文档由 MACF 自动生成。详细共识见 shared_memory.json。*
"""

    def cleanup(self):
        """清理所有 Agent"""
        self._save_debate_log()
        # 先通知 Agent 退出
        self._shutdown_agents()
        # 等待一下让消息送达
        time.sleep(1)
        for agent in self.agents.values():
            agent.cleanup()
        self.broker.close()
        print("🧹 Orchestrator 已清理")
