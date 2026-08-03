#!/usr/bin/env python3
"""
MACF Agent 独立进程启动脚本

运行方式：
    # 终端 1 - 启动 Agent A
    python3 run_agent.py --id agent-a --config config/debate.yaml

    # 终端 2 - 启动 Agent B
    python3 run_agent.py --id agent-b --config config/debate.yaml

    # 终端 3 - 启动协调器（触发任务）
    python3 run_orchestrator.py --config config/debate.yaml
"""

import os
import sys
import yaml
import re
import signal
import time
import argparse
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

from macf.agent import Agent
from macf.broker import MessageBroker


def load_config(config_path: str) -> dict:
    """加载 YAML 配置文件，解析环境变量"""
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    def replace_env(match):
        env_var = match.group(1)
        value = os.environ.get(env_var, "")
        if not value:
            print(f"⚠️ 环境变量 {env_var} 未设置!")
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


def main():
    parser = argparse.ArgumentParser(description="MACF Agent 独立进程")
    parser.add_argument("--id", required=True, help="Agent ID (如 agent-a)")
    parser.add_argument("--config", default="./config/debate.yaml", help="配置文件路径")
    args = parser.parse_args()

    print("=" * 60)
    print(f"🤖 MACF Agent - 独立进程模式")
    print(f"   Agent ID: {args.id}")
    print(f"   配置文件: {args.config}")
    print("=" * 60)
    print()

    # 加载配置
    config = load_config(args.config)

    # 准备工作区（复制 target 文件）
    setup_workspace(config)

    # 查找 Agent 配置
    agent_cfg = None
    for a in config["agents"]:
        if a["id"] == args.id:
            agent_cfg = a
            break

    if not agent_cfg:
        print(f"❌ 未找到 Agent ID: {args.id}")
        sys.exit(1)

    # 获取模型配置
    model_cfg = config["models"][agent_cfg["model"]]

    # 初始化 Redis
    broker_config = config.get("broker", {})
    broker = MessageBroker(
        host=broker_config.get("host", "localhost"),
        port=broker_config.get("port", 6379),
    )

    # 创建 Agent
    agent = Agent(
        agent_id=agent_cfg["id"],
        name=agent_cfg["name"],
        role=agent_cfg["role"],
        model_config=model_cfg,
        workspace=agent_cfg.get("workspace", f"./workspace/{args.id}"),
        tools=agent_cfg.get("tools", []),
        broker=broker,
    )

    # 处理 Ctrl+C
    def signal_handler(sig, frame):
        print(f"\n\n⛔ 收到中断信号，正在关闭 Agent [{args.id}]...")
        agent.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    print(f"\n✅ Agent [{args.id}] 已启动，等待消息中...")
    print(f"   按 Ctrl+C 退出\n")

    # 持续监听消息，直到收到退出通知
    try:
        while True:
            time.sleep(1)
            # 检查是否收到退出通知
            if agent._should_exit:
                print(f"\n👋 Agent [{args.id}] 收到退出通知，正在退出...")
                break
    except KeyboardInterrupt:
        pass
    finally:
        agent.cleanup()


if __name__ == "__main__":
    main()
