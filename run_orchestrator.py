#!/usr/bin/env python3
"""
MACF Orchestrator - 协调器

完整流程：
1. 触发 Agent A + Agent B 讨论
2. 监控讨论过程
3. 达成共识 → 生成 final_plan.md
4. 调用 Claude Code 执行方案

运行方式：
    python3 run_orchestrator.py --config config/debate.yaml
"""

import os
import sys
import yaml
import re
import time
import json
import subprocess
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 自动加载 .env 文件
def load_env():
    """从 .env 文件加载环境变量"""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())

load_env()

from macf.protocol import Message, MessageType
from macf.broker import MessageBroker


def load_config(config_path: str) -> dict:
    """加载 YAML 配置文件"""
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    def replace_env(match):
        env_var = match.group(1)
        value = os.environ.get(env_var, "")
        return value

    content = re.sub(r"\$\{(\w+)\}", replace_env, content)
    return yaml.safe_load(content)


def setup_workspace(config: dict):
    """准备工作区：复制 target 文件到各 Agent 工作区"""
    from pathlib import Path
    import shutil

    print("📦 设置工作区...\n")

    for agent_cfg in config["agents"]:
        workspace = Path(agent_cfg["workspace"])
        workspace.mkdir(parents=True, exist_ok=True)

        target_dir = Path("./workspace/target")
        if target_dir.exists():
            for target_file in target_dir.iterdir():
                if target_file.is_file():
                    dest = workspace / target_file.name
                    shutil.copy2(target_file, dest)
                    print(f"   ✅ {target_file.name} → {workspace}")

    print()


def generate_final_plan(task: str, messages: list, consensus_reached: bool) -> str:
    """生成最终方案文档"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 提取关键消息
    proposals = [m for m in messages if m.type == MessageType.PROPOSAL]
    approvals = [m for m in messages if m.type == MessageType.APPROVAL]
    final_proposal = proposals[-1] if proposals else None
    final_approval = approvals[-1] if approvals else None

    content = f"""# 最终修复方案

> **生成时间**: {now}
> **任务**: {task}
> **共识**: {"已达成 ✅" if consensus_reached else "未达成（超时）"}
> **讨论轮次**: {len(messages)} 条消息

---

## 1. 任务概述

{task}

## 2. 讨论摘要

本次讨论共 {len(messages)} 轮，最终{"达成共识" if consensus_reached else "未达成完全共识"}。

## 3. 修复方案

"""

    if final_proposal:
        proposal_content = final_proposal.payload.get("content", "")
        content += f"""### 3.1 安全专家方案

{proposal_content}

"""

    if final_approval:
        approval_content = final_approval.payload.get("content", "")
        content += f"""### 3.2 开发者评审意见

{approval_content}

"""

    content += """---

## 4. 实施建议

### 4.1 优先级

1. **严重 (Critical)**: 立即修复
2. **高危 (High)**: 尽快修复
3. **中危 (Medium)**: 计划修复

### 4.2 实施步骤

1. 按优先级逐一修复
2. 每修复一个漏洞后进行测试
3. 全部修复后安全回归测试

---

## 5. 讨论记录

| 轮次 | 发送者 | 类型 | 摘要 |
|------|--------|------|------|
"""

    for i, msg in enumerate(messages, 1):
        summary = msg.payload.get("summary", msg.payload.get("content", "")[:50])
        content += f"| {i} | {msg.from_agent} | {msg.type.value} | {summary} |\n"

    content += f"""

---

*本文档由 MACF 自动生成。*
"""

    return content


def run_claude_code(plan_path: str, workspace: str):
    """调用 Claude Code 执行方案"""
    print(f"\n{'='*60}")
    print("🤖 启动 Claude Code 执行方案")
    print(f"{'='*60}\n")

    # 构建 Claude Code 的 prompt
    prompt = f"请读取 {plan_path} 方案文档，按照方案修复代码。按优先级逐一修复，每修复一个漏洞后运行测试验证，全部修复后生成修复报告。"

    print(f"📋 方案文件: {plan_path}")
    print(f"📋 工作目录: {workspace}\n")

    # 使用 claude CLI 非交互模式执行
    try:
        # 检查 claude 是否可用
        check = subprocess.run(
            ["which", "claude"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if check.returncode != 0:
            raise FileNotFoundError("claude CLI not found")

        print("⏳ Claude Code 执行中...（可能需要几分钟）")
        print("   输出将直接显示在终端...\n")

        # 使用 Popen 执行，不捕获输出（直接显示在终端）
        process = subprocess.Popen(
            ["claude", "-p", "--dangerously-skip-permissions", prompt],
            cwd=workspace,
        )

        try:
            process.wait(timeout=600)
            print(f"\n✅ Claude Code 执行完成 (返回码: {process.returncode})")
        except subprocess.TimeoutExpired:
            process.kill()
            print("⏰ Claude Code 执行超时")

    except FileNotFoundError:
        print("⚠️ 未找到 claude CLI")
    except Exception as e:
        print(f"❌ Claude Code 执行失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="MACF Orchestrator")
    parser.add_argument("--config", default="./config/debate.yaml", help="配置文件路径")
    parser.add_argument("--no-claude", action="store_true", help="不调用 Claude Code（仅生成方案）")
    args = parser.parse_args()

    print("=" * 60)
    print("🎯 MACF Orchestrator - 协调器")
    print(f"   配置文件: {args.config}")
    print(f"   模式: {'仅生成方案' if args.no_claude else '讨论 + Claude Code 执行'}")
    print("=" * 60)
    print()

    config_data = load_config(args.config)

    # 准备工作区（复制 target 文件到各 Agent 工作区）
    setup_workspace(config_data)

    # 初始化 Redis
    broker_config = config_data.get("broker", {})
    broker = MessageBroker(
        host=broker_config.get("host", "localhost"),
        port=broker_config.get("port", 6379),
    )

    # 获取 Agent 配置
    starter_id = config_data["agents"][0]["id"]
    responder_id = config_data["agents"][1]["id"] if len(config_data["agents"]) > 1 else None

    # 从配置文件读取任务描述
    task_config = config_data.get("task", {})
    task_name = task_config.get("name", "代码审查")
    task_desc = task_config.get("description", "请审查工作区中的代码文件。")

    # 补充通用规则
    task = f"""
{task_desc}

⚠️ 讨论规则：
- 只讨论工作区中实际存在的文件，不要假设或编造文件名
- 每次回复控制在 500 字以内，聚焦核心分歧点
- 必须使用 send_message 工具发送回复
- 你只负责讨论和出方案，不需要修改代码
"""

    print(f"📋 任务: {task_name}")
    print(f"   发起者: {starter_id}")
    print(f"   审查者: {responder_id}")
    print()

    # 发送任务给发起者
    print(f"🚀 发送任务给 {starter_id}...")
    task_msg = Message(
        from_agent="orchestrator",
        to_agent=starter_id,
        msg_type=MessageType.TASK_START,
        payload={
            "content": task,
            "summary": "开始代码安全审查任务",
            "responder": responder_id,
        },
    )
    broker.publish(task_msg)

    # 监控消息交换
    print(f"\n⏳ 监控 Agent 对话中...\n")
    msg_count = 0
    start_time = time.time()
    consensus_reached = False
    messages_received = []

    def monitor_handler(msg: Message):
        nonlocal msg_count, consensus_reached
        msg_count += 1
        messages_received.append(msg)
        print(f"[{msg_count}] {msg.from_agent} → {msg.to_agent}: [{msg.type.value}] {msg.payload.get('content', '')[:60]}...")

        if msg.type == MessageType.APPROVAL:
            content = msg.payload.get("content", "")
            keywords = config_data.get("debate", {}).get("consensus_keywords", ["同意", "approval"])
            if any(kw in content for kw in keywords):
                consensus_reached = True
                print(f"\n🎉 达成共识! Agent [{msg.from_agent}] 表示同意")

    # 订阅所有 Agent 的 channel（直接订阅，比模式订阅更可靠）
    for agent_cfg in config_data["agents"]:
        agent_id = agent_cfg["id"]
        broker.subscribe(agent_id, monitor_handler)
    broker.start_listener()

    # 等待讨论完成
    max_stall_count = 60  # 120秒
    stall_count = 0
    last_count = 0

    try:
        while True:
            time.sleep(2)
            if msg_count > last_count:
                last_count = msg_count
                stall_count = 0
            else:
                stall_count += 1
                if stall_count > max_stall_count:
                    print("\n⚠️ 讨论停滞")
                    break

            if consensus_reached and msg_count > 4:
                # 共识后多等几秒
                time.sleep(3)
                break

    except KeyboardInterrupt:
        print(f"\n⛔ 用户中断")

    # 生成最终方案
    print(f"\n📝 生成最终方案文档...")
    plan_content = generate_final_plan(task, messages_received, consensus_reached)
    plan_path = "./workspace/final_plan.md"
    os.makedirs("./workspace", exist_ok=True)
    with open(plan_path, "w", encoding="utf-8") as f:
        f.write(plan_content)
    print(f"✅ 方案已保存: {plan_path} ({len(plan_content.splitlines())} 行)")

    # 关闭 Redis（在调用 Claude Code 之前）
    broker.close()

    # 调用 Claude Code 执行
    if not args.no_claude:
        run_claude_code(plan_path, "./workspace")
    else:
        print(f"\n💡 跳过 Claude Code 执行（--no-claude 模式）")
        print(f"   手动执行: cat {plan_path} | claude --file -")

    print(f"\n{'='*60}")
    print("🏁 MACF 流程完成!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
