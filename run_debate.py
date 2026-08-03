#!/usr/bin/env python3
"""
MACF Debate - 讨论模式（单进程）

Agent 之间讨论，输出最终方案文档，供 Claude Code 执行。

运行方式:
    python3 run_debate.py
"""

import os
import sys
import yaml
import shutil
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

from macf.orchestrator import DebateOrchestrator


def load_config(config_path: str) -> dict:
    """加载 YAML 配置文件，解析环境变量"""
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    import re
    def replace_env(match):
        env_var = match.group(1)
        value = os.environ.get(env_var, "")
        if not value:
            print(f"⚠️ 环境变量 {env_var} 未设置!")
        return value

    content = re.sub(r"\$\{(\w+)\}", replace_env, content)
    return yaml.safe_load(content)


def setup_workspace(config: dict):
    """准备工作区"""
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
    print("=" * 60)
    print("🎯 MACF - Multi-Agent Collaboration Framework")
    print("   讨论模式：Agent 讨论 → 输出方案 → Claude Code 执行")
    print("=" * 60)
    print()

    # 检查环境变量
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("❌ 请设置环境变量: DEEPSEEK_API_KEY")
        sys.exit(1)

    if not os.environ.get("LONGCAT_API_KEY"):
        print("❌ 请设置环境变量: LONGCAT_API_KEY")
        sys.exit(1)

    # 加载配置
    config = load_config("./config/debate.yaml")

    # 准备工作区
    setup_workspace(config)

    # 创建并运行 Orchestrator
    orchestrator = DebateOrchestrator(config)

    # 定义任务（从配置读取）
    task = config.get("task", {}).get("description", "请审查工作区中的代码文件。")

    # 补充通用规则
    task += """

⚠️ 讨论规则：
- 只讨论工作区中实际存在的文件，不要假设或编造文件名
- 每次回复控制在 500 字以内，聚焦核心分歧点
- 必须使用 send_message 工具发送回复
- 你只负责讨论和出方案，不需要修改代码
"""

    try:
        orchestrator.run_debate(
            task=task,
            starter="agent-a",
            responder="agent-b",
        )
    except KeyboardInterrupt:
        print("\n\n⛔ 用户中断")
    finally:
        orchestrator.cleanup()

    # 输出交接提示
    print("\n" + "=" * 60)
    print("📋 MACF 讨论完成!")
    print("=" * 60)
    print()
    print("📄 最终方案文档: ./workspace/final_plan.md")
    print("📋 讨论记录: ./workspace/debate_log.json")
    print()
    print("👉 下一步：将方案提交给 Claude Code 执行")
    print()
    print("   方式 1: 手动复制方案到 Claude Code")
    print("   方式 2: 在 Claude Code 中运行:")
    print("      cat workspace/final_plan.md | claude --file -")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
