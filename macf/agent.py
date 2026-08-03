"""
MACF Agent - 独立的智能体实例

每个 Agent 是独立进程，拥有自己的：
- Claude/LLM 会话
- 工作区
- 消息订阅
- 角色和工具权限
"""

import os
import json
import time
import re
from typing import Optional
from openai import OpenAI

from .protocol import Message, MessageType
from .broker import MessageBroker
from .tools import ToolExecutor
from .shared_memory import SharedMemory


class Agent:
    """MACF 智能体"""

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
    ):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.tools = tools
        self.broker = broker
        self.max_tool_rounds = max_tool_rounds

        # 初始化 LLM 客户端
        self.client = OpenAI(
            api_key=model_config["api_key"],
            base_url=model_config["base_url"],
            timeout=120.0,
        )
        self.model = model_config["model"]

        # 初始化工具执行器
        self.tool_executor = ToolExecutor(workspace)

        # 对话历史（滑动窗口，保留最近 N 轮）
        self.conversation_history = []
        self._max_history = 6  # 最多保留 6 条消息（避免上下文过长导致 LLM 困惑）

        # 标记：是否正在回复对方消息
        self._is_replying_to_peer = False

        # 已处理消息 ID 集合（去重）
        self._processed_msg_ids = set()

        # 已读取文件缓存（避免重复读取）
        self._file_cache = {}

        # 是否已注入文件内容（避免每轮重复注入）
        self._file_injected = False

        # 是否应该退出（收到退出通知时设为 True）
        self._should_exit = False

        # 共享记忆——Agent 之间的桥梁
        self.shared_memory = SharedMemory()

        # 订阅消息
        self.broker.subscribe(agent_id, self._on_message)
        self.broker.start_listener()

        print(f"🤖 Agent [{agent_id}] ({name}) 已启动 | 模型: {self.model}")

    def _system_prompt(self) -> str:
        """生成系统提示词（注入共享记忆）"""
        # 获取当前工作区文件列表（防幻觉）
        try:
            current_files = self.tool_executor.list_files()
        except Exception:
            current_files = "(无法读取)"

        # 获取共享记忆上下文
        shared_context = self.shared_memory.get_full_context()

        return f"""你是 {self.name}。{self.role}

⚠️ 必须遵守：
1. 每次回复必须调用 send_message 工具（这是唯一发送消息的方式）
2. 工作区文件: {current_files}（只讨论实际存在的文件）
3. 回复控制在 500 字以内，聚焦核心分歧点
4. 不要重复讨论已达成的共识，必须针对对方的具体观点回应

{shared_context}"""

    def _get_tool_definitions(self) -> list:
        """获取工具定义（包括通信工具）"""
        all_tools = self.tool_executor.get_tool_definitions()
        authorized_tools = [t for t in all_tools if t["function"]["name"] in self.tools]

        # 添加通信工具
        authorized_tools.append({
            "type": "function",
            "function": {
                "name": "send_message",
                "description": "发送消息给其他 Agent（必须使用此工具回复）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to_agent": {
                            "type": "string",
                            "description": "目标 Agent ID (agent-a 或 agent-b)",
                            "enum": ["agent-a", "agent-b"],
                        },
                        "msg_type": {
                            "type": "string",
                            "description": "消息类型",
                            "enum": [
                                "proposal", "critique", "revision",
                                "approval", "rejection", "task_complete",
                            ],
                        },
                        "content": {
                            "type": "string",
                            "description": "消息正文内容",
                        },
                    },
                    "required": ["to_agent", "msg_type", "content"],
                },
            },
        })

        return authorized_tools

    def _summarize_file(self, file_context: str) -> str:
        """生成文件简短摘要（用于后续轮次提醒）"""
        # 提取文件名
        lines = file_context.strip().split("\n")
        filename = "unknown"
        for line in lines:
            if line.startswith("文件:"):
                filename = line.replace("文件:", "").strip()
                break
        # 提取代码中的函数/类定义作为摘要
        definitions = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("def ") or stripped.startswith("class ") or stripped.startswith("@app."):
                definitions.append(stripped[:60])
        # 最多取 5 个定义
        def_summary = ", ".join(definitions[:5]) if definitions else "包含多个函数定义"
        return f"{filename} ({def_summary})"

    def _trim_history(self):
        """滑动窗口：保留最近 N 条消息，保持 tool_calls/tool 配对完整"""
        if len(self.conversation_history) <= self._max_history:
            return

        # 保留第一条消息（包含文件内容/摘要），只裁剪后续对话
        # 这样 LLM 不会忘记工作区文件内容
        first_msg = self.conversation_history[0]
        remaining = self.conversation_history[1:]

        # 从 remaining 中保留最近 N-1 条
        if len(remaining) > self._max_history - 1:
            cutoff = len(remaining) - (self._max_history - 1)
            # 从后往前找，找到第一个 role=user 的位置
            for i in range(cutoff, len(remaining)):
                if remaining[i].get("role") == "user":
                    cutoff = i
                    break
            remaining = remaining[cutoff:]

        self.conversation_history = [first_msg] + remaining

    def _on_message(self, message: Message):
        """收到消息时的回调"""
        # 去重：忽略已处理的消息
        if message.id in self._processed_msg_ids:
            print(f"⏭️ [{self.agent_id}] 忽略重复消息: {message.id}")
            return
        self._processed_msg_ids.add(message.id)

        # 忽略自己发的消息
        if message.from_agent == self.agent_id:
            return

        # 处理 orchestrator 的收敛推动消息
        if message.from_agent == "orchestrator" and message.type == MessageType.TASK_REVIEW:
            print(f"\n⚡ [{self.agent_id}] 收到收敛推动消息")
            self._handle_convergence_push(message)
            return

        # 忽略来自 orchestrator 的其他非任务消息
        if message.from_agent == "orchestrator" and message.type != MessageType.TASK_START:
            return

        print(f"\n{'='*60}")
        print(f"📨 [{self.agent_id}] 收到来自 [{message.from_agent}] 的消息")
        print(f"   类型: {message.type.value}")
        print(f"   内容: {message.payload.get('content', '')[:200]}...")
        print(f"{'='*60}\n")

        # 处理任务启动消息
        if message.type == MessageType.TASK_START:
            self._handle_task_start(message)
            return

        # 处理退出通知
        if message.from_agent == "orchestrator" and message.type == MessageType.TASK_COMPLETE:
            print(f"\n🛑 [{self.agent_id}] 收到退出通知，准备退出...")
            self._should_exit = True
            return

        # 处理 orchestrator 的收敛推动消息
        if message.from_agent == "orchestrator" and message.type == MessageType.TASK_REVIEW:
            print(f"\n⚡ [{self.agent_id}] 收到收敛推动消息")
            self._handle_convergence_push(message)
            return

        # 忽略来自 orchestrator 的其他非任务消息
        if message.from_agent == "orchestrator" and message.type not in (MessageType.TASK_START, MessageType.TASK_COMPLETE):
            return

        self._is_replying_to_peer = True

        # 构建用户消息
        context = message.payload.get("content", "")

        # 从消息中提取共识点并写入共享记忆
        self._extract_and_save_consensus(message)

        # 首次注入完整文件，后续只注入简短摘要
        if not self._file_injected:
            file_context = self._auto_read_files()
            if file_context:
                context += f"\n\n[工作区文件]\n{file_context}"
                # 生成简短摘要供后续使用
                self._file_summary = self._summarize_file(file_context)
                self._file_injected = True
                # 标记文件已读
                for fname in self._file_cache:
                    self.shared_memory.mark_file_read(fname, self.agent_id)
        elif hasattr(self, '_file_summary') and self._file_summary:
            # 后续轮次只注入摘要，避免 LLM 误以为是新文件
            context += f"\n\n[工作区文件回顾: {self._file_summary}]"

        # 注入共享记忆上下文
        context += f"\n\n{self.shared_memory.get_full_context()}"

        self.conversation_history.append({
            "role": "user",
            "content": f"[来自 {message.from_agent} - {message.type.value}]\n{context}",
        })

        # 更新消息计数
        self.shared_memory.increment_message_count()

        # 滑动窗口裁剪
        self._trim_history()

        # 直接调用 LLM 并让它使用 send_message 回复
        self._generate_reply()

    def _handle_task_start(self, message: Message):
        """处理任务启动消息"""
        print(f"🚀 [{self.agent_id}] 收到任务启动指令")
        responder = message.payload.get("responder", "agent-b" if self.agent_id == "agent-a" else "agent-a")

        # 自动读取文件（带缓存）
        file_context = self._auto_read_files()
        context = message.payload.get("content", "")
        if file_context:
            context += f"\n\n[工作区文件]\n{file_context}"

        self.conversation_history.append({
            "role": "user",
            "content": f"{context}\n\n完成后请将结果发送给 {responder}",
        })

        # 滑动窗口裁剪
        self._trim_history()

        # 使用工具调用循环（发起任务可能需要多轮工具调用）
        self._process_conversation()

    def _handle_convergence_push(self, message: Message):
        """处理收敛推动消息——读取共识文件后给出最终确认"""
        print(f"🎯 [{self.agent_id}] 处理收敛推动...")

        # 读取共识文件
        consensus_summary = "（暂无共识）"
        try:
            import json
            with open("./workspace/consensus.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                points = data.get("agreed_points", [])
                if points:
                    consensus_summary = "已确认的共识点：\n"
                    for i, p in enumerate(points, 1):
                        consensus_summary += f"{i}. {p}\n"
        except Exception:
            pass

        # 构建推动消息
        context = message.payload.get("content", "")
        context += f"\n\n[共识记录]\n{consensus_summary}"
        context += "\n\n请基于以上共识，给出你的最终确认（approval）或最后异议。"

        self.conversation_history.append({
            "role": "user",
            "content": context,
        })

        # 滑动窗口裁剪
        self._trim_history()

        # 生成回复
        self._is_replying_to_peer = True
        self._generate_reply()

    def _auto_read_files(self) -> str:
        """自动读取工作区文件（带缓存，避免重复读取）"""
        try:
            files = self.tool_executor.list_files()
            if not files or files == "(空工作区)":
                return ""

            for fname in files.split("\n"):
                fname = fname.strip()
                if fname.endswith((".py", ".js", ".ts", ".go", ".java")):
                    # 检查缓存
                    cache_key = fname
                    if cache_key in self._file_cache:
                        return self._file_cache[cache_key]

                    content = self.tool_executor.read_file(fname)
                    if not content.startswith("❌"):
                        result = f"文件: {fname}\n```\n{content[:3000]}\n```"
                        self._file_cache[cache_key] = result
                        return result
            return ""
        except Exception:
            return ""

    def _extract_and_save_consensus(self, message: Message):
        """从消息中提取共识点并保存到共享记忆（过滤噪声，只保留技术决策）"""
        content = message.payload.get("content", "")
        msg_type = message.type

        # 过滤掉非技术内容（噪声过滤）
        noise_indicators = [
            "讨论摘要", "已确认", "共识点", "让我先读取",
            "我需要先", "让我分析", "看起来", "用户要求我",
            "Let me", "I need to", "I'm agent", "agent-a", "agent-b",
        ]
        if any(noise in content for noise in noise_indicators):
            # 跳过纯摘要/元讨论消息，但可能包含技术内容的混合消息除外
            if not any(kw in content for kw in ["POST ", "GET ", "PUT ", "DELETE ", "/api/", "CREATE TABLE"]):
                return

        # 从 approval 消息中提取共识
        if msg_type == MessageType.APPROVAL:
            consensus_keywords = ["同意", "确认", "接受", "认可", "没问题", "可以实施", "达成共识", "✅"]
            for line in content.split("\n"):
                line = line.strip()
                # 过滤太短或太长的行
                if not line or len(line) < 8 or len(line) > 200:
                    continue
                # 过滤噪声行
                if any(noise in line for noise in noise_indicators):
                    continue
                for kw in consensus_keywords:
                    if kw in line:
                        clean = line.replace("**", "").replace("✅", "").replace("-", "").strip()
                        if clean and len(clean) > 8:
                            self.shared_memory.add_agreed_point(clean, message.from_agent)
                        break

        # 从 revision 消息中提取修正后的共识
        elif msg_type == MessageType.REVISION:
            revision_keywords = ["确认", "调整为", "修改为", "改为", "接受", "采纳"]
            for line in content.split("\n"):
                line = line.strip()
                if not line or len(line) < 8 or len(line) > 200:
                    continue
                if any(noise in line for noise in noise_indicators):
                    continue
                for kw in revision_keywords:
                    if kw in line:
                        clean = line.replace("**", "").replace("✅", "").replace("-", "").strip()
                        if clean and len(clean) > 8:
                            self.shared_memory.add_agreed_point(clean, message.from_agent)
                        break

    def _generate_reply(self):
        """生成回复（带文本解析 fallback 和指数退避重试）"""
        retry_count = 0
        max_retries = 3
        retry_target = self._get_reply_target()

        while retry_count < max_retries:
            # 始终强制调用 send_message 工具
            tool_choice = {"type": "function", "function": {"name": "send_message"}}

            try:
                print(f"🌐 [{self.agent_id}] 调用 LLM (尝试 {retry_count + 1})...")
                llm_start = time.time()
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._system_prompt()},
                        *self.conversation_history,
                    ],
                    tools=self._get_tool_definitions(),
                    tool_choice=tool_choice,
                    temperature=0.5 if retry_count > 0 else 0.7,  # 重试时降低温度
                    max_tokens=4096,
                )
                elapsed = time.time() - llm_start
                print(f"✅ [{self.agent_id}] LLM 响应完成 ({elapsed:.1f}s)")
            except Exception as e:
                elapsed = time.time() - llm_start
                print(f"❌ [{self.agent_id}] API 调用失败 ({elapsed:.1f}s): {e}")
                # 指数退避
                wait_time = min(2 ** retry_count, 30)
                print(f"   ⏳ {wait_time}s 后重试...")
                time.sleep(wait_time)
                retry_count += 1
                continue

            assistant_message = response.choices[0].message
            actual_content = assistant_message.content or ""

            # 检查是否有 send_message 工具调用
            has_send_message = False
            if assistant_message.tool_calls:
                for tc in assistant_message.tool_calls:
                    if tc.function.name == "send_message":
                        has_send_message = True
                        try:
                            args = json.loads(tc.function.arguments)
                            to_agent = args.get("to_agent", retry_target)
                            msg_type_str = args.get("msg_type", "critique")
                            content = args.get("content", "")
                            try:
                                msg_type = MessageType(msg_type_str)
                            except ValueError:
                                msg_type = MessageType.CRITIQUE
                            self._force_send(to_agent, content, msg_type)
                        except json.JSONDecodeError:
                            # 参数解析失败，fallback 到文本解析
                            print(f"   ⚠️ 工具参数解析失败，使用文本 fallback")
                            self._send_from_text(actual_content, retry_target)

            # 如果模型调用了 send_message，完成
            if has_send_message:
                self._is_replying_to_peer = False
                return

            # 模型没有调用 send_message，使用文本解析 fallback
            print(f"   📝 模型未调用工具，使用文本解析 fallback")
            if actual_content and len(actual_content) > 20:
                self._send_from_text(actual_content, retry_target)
                self._is_replying_to_peer = False
                return

            # 空内容，重试
            retry_count += 1
            print(f"🔄 [{self.agent_id}] 内容为空，重试 {retry_count}")

        # 重试耗尽，发送默认消息
        print(f"⚠️ [{self.agent_id}] 重试耗尽，发送默认确认消息")
        self._force_send(retry_target, "我同意你的观点，可以继续推进。", MessageType.APPROVAL)
        self._is_replying_to_peer = False

    def _send_from_text(self, content: str, target: str):
        """从文本中提取结构化信息并发送消息"""
        # 判断消息类型
        msg_type = MessageType.CRITIQUE
        content_lower = content.lower()
        if any(kw in content for kw in ["同意", "确认", "接受", "认可", "没问题"]):
            msg_type = MessageType.APPROVAL
        elif any(kw in content for kw in ["修订", "修改", "补充", "调整"]):
            msg_type = MessageType.REVISION
        elif any(kw in content for kw in ["方案", "建议", "提议", "设计"]):
            msg_type = MessageType.PROPOSAL

        # 限制长度
        if len(content) > 2000:
            content = content[:2000] + "\n...(已截断)"

        self._force_send(target, content, msg_type)

    def _get_reply_target(self) -> str:
        """根据对话历史判断回复目标"""
        # 从对话历史中找到最后一条来自对方的消息
        for msg in reversed(self.conversation_history):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if "来自 agent-a" in content:
                    return "agent-a"
                elif "来自 agent-b" in content:
                    return "agent-b"
        # 默认发给对方
        return "agent-b" if self.agent_id == "agent-a" else "agent-a"

    def _force_send(self, to_agent: str, content: str, msg_type: MessageType):
        """强制发送消息给对方"""
        # 如果 to_agent 是自己，自动纠正
        if to_agent == self.agent_id:
            to_agent = self._get_reply_target()
        message = Message(
            from_agent=self.agent_id,
            to_agent=to_agent,
            msg_type=msg_type,
            payload={"content": content, "summary": content[:50]},
        )
        self.broker.publish(message)
        print(f"📤 [{self.agent_id}] 发送给 {to_agent} ({msg_type.value})")

    def start_task(self, task_description: str, to_agent: str = "agent-b"):
        """主动发起任务"""
        print(f"\n🚀 [{self.agent_id}] 开始任务: {task_description}")

        # 自动读取文件
        file_context = self._auto_read_files()
        context = task_description
        if file_context:
            context += f"\n\n[工作区文件]\n{file_context}"

        self.conversation_history.append({
            "role": "user",
            "content": f"请开始以下任务:\n{context}\n\n完成后请将结果发送给 {to_agent}",
        })

        # 使用工具调用循环（发起任务可能需要多轮工具调用）
        self._process_conversation()

    def _process_conversation(self):
        """处理对话（支持多轮工具调用，带 fallback 和退避）"""
        tool_rounds = 0
        has_sent_message = False
        retry_count = 0

        while tool_rounds < self.max_tool_rounds:
            # 滑动窗口裁剪（防止上下文爆炸）
            self._trim_history()
            try:
                print(f"🌐 [{self.agent_id}] 调用 LLM (轮次 {tool_rounds + 1})...")
                llm_start = time.time()
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._system_prompt()},
                        *self.conversation_history,
                    ],
                    tools=self._get_tool_definitions(),
                    tool_choice="auto",
                    temperature=0.5 if retry_count > 0 else 0.7,
                    max_tokens=4096,
                )
                elapsed = time.time() - llm_start
                print(f"✅ [{self.agent_id}] LLM 响应完成 ({elapsed:.1f}s)")
                retry_count = 0  # 成功重置
            except Exception as e:
                elapsed = time.time() - llm_start
                print(f"❌ [{self.agent_id}] API 调用失败 ({elapsed:.1f}s): {e}")
                # 指数退避
                wait_time = min(2 ** retry_count, 30)
                print(f"   ⏳ {wait_time}s 后重试...")
                time.sleep(wait_time)
                retry_count += 1
                if retry_count >= 3:
                    print(f"   ⚠️ 重试耗尽，跳过本轮")
                    return
                continue

            assistant_message = response.choices[0].message

            # 处理推理模型
            actual_content = assistant_message.content
            if actual_content is None and hasattr(assistant_message, 'reasoning_content'):
                actual_content = assistant_message.reasoning_content
            actual_content = actual_content or "(无内容)"

            # 如果没有工具调用，使用文本 fallback
            if not assistant_message.tool_calls:
                print(f"   📝 无工具调用，使用文本 fallback")
                if actual_content != "(无内容)" and len(actual_content) > 20:
                    self._send_from_text(actual_content, self._get_reply_target())
                    return
                # 空内容，继续下一轮
                tool_rounds += 1
                continue

            # 有工具调用
            tool_calls_list = []
            for tc in assistant_message.tool_calls:
                tool_calls_list.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })

            self.conversation_history.append({
                "role": "assistant",
                "content": actual_content,
                "tool_calls": tool_calls_list,
            })

            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    print(f"   ⚠️ 参数解析失败: {tool_call.function.arguments[:50]}")
                    tool_args = {}

                print(f"🔧 [{self.agent_id}] 调用工具: {tool_name}({tool_args})")

                if tool_name == "send_message":
                    result = self._handle_send_message(tool_args)
                    has_sent_message = True
                else:
                    if tool_name in self.tools:
                        result = self.tool_executor.execute_tool(tool_name, tool_args)
                    else:
                        result = f"⛔ 无权使用工具: {tool_name}"

                print(f"   结果: {result[:100]}...")

                self.conversation_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            tool_rounds += 1

            # 发送消息后立即退出，避免一轮发多条
            if has_sent_message:
                return

    def _handle_send_message(self, args: dict) -> str:
        """处理发送消息"""
        to_agent = args.get("to_agent", self._get_reply_target())
        msg_type_str = args.get("msg_type", "critique")
        content = args.get("content", "")

        # 防止发给自己
        if to_agent == self.agent_id:
            to_agent = self._get_reply_target()

        try:
            msg_type = MessageType(msg_type_str)
        except ValueError:
            msg_type = MessageType.CRITIQUE

        message = Message(
            from_agent=self.agent_id,
            to_agent=to_agent,
            msg_type=msg_type,
            payload={"content": content, "summary": content[:50]},
        )

        success = self.broker.publish(message)
        return f"✅ 消息已发送给 {to_agent}" if success else "❌ 发送失败"

    def send_direct_message(self, to_agent: str, content: str, msg_type: MessageType = MessageType.TASK_COMPLETE):
        """直接发送消息（不经过 LLM）"""
        message = Message(
            from_agent=self.agent_id,
            to_agent=to_agent,
            msg_type=msg_type,
            payload={"content": content, "summary": content[:50]},
        )
        self.broker.publish(message)

    def cleanup(self):
        """清理资源"""
        self.broker.stop_listener()
        print(f"🧹 Agent [{self.agent_id}] 已清理")
