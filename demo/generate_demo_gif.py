"""
MACF Demo GIF Generator

生成 MACF 工作流程演示动画。
需要安装: pip install matplotlib pillow imageio
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
from PIL import Image
import io

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Heiti SC', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def create_frame(title, agents_active, messages, consensus, step, total_steps):
    """创建单帧"""
    fig, ax = plt.subplots(1, 1, figsize=(12, 7))
    ax.set_xlim(0, 12)
    set_ylim = 7
    ax.set_ylim(0, set_ylim)
    ax.axis('off')
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#0d1117')

    # 标题
    ax.text(6, 6.5, title, fontsize=18, fontweight='bold',
            ha='center', va='center', color='#58a6ff')

    # 进度条
    progress = step / total_steps
    ax.add_patch(FancyBboxPatch((1, 5.8), 10, 0.3, boxstyle="round,pad=0.05",
                                facecolor='#21262d', edgecolor='#30363d'))
    ax.add_patch(FancyBboxPatch((1, 5.8), 10 * progress, 0.3, boxstyle="round,pad=0.05",
                                facecolor='#238636', edgecolor='none'))
    ax.text(6, 5.95, f'Step {step}/{total_steps}', fontsize=10,
            ha='center', va='center', color='#8b949e')

    # Agent A
    a_color = '#58a6ff' if agents_active[0] else '#30363d'
    a_box = FancyBboxPatch((1, 3.5), 3.5, 1.8, boxstyle="round,pad=0.1",
                           facecolor=a_color, edgecolor='#58a6ff', linewidth=2)
    ax.add_patch(a_box)
    ax.text(2.75, 4.8, 'Agent A', fontsize=14, fontweight='bold',
            ha='center', va='center', color='white')
    ax.text(2.75, 4.2, 'Frontend Architect', fontsize=10,
            ha='center', va='center', color='#8b949e')

    # Agent B
    b_color = '#a371f7' if agents_active[1] else '#30363d'
    b_box = FancyBboxPatch((7.5, 3.5), 3.5, 1.8, boxstyle="round,pad=0.1",
                           facecolor=b_color, edgecolor='#a371f7', linewidth=2)
    ax.add_patch(b_box)
    ax.text(9.25, 4.8, 'Agent B', fontsize=14, fontweight='bold',
            ha='center', va='center', color='white')
    ax.text(9.25, 4.2, 'Backend Engineer', fontsize=10,
            ha='center', va='center', color='#8b949e')

    # 消息箭头
    if messages:
        for i, msg in enumerate(messages[-3:]):  # 最近 3 条
            y_pos = 2.5 - i * 0.5
            arrow_color = '#238636' if msg.get('type') == 'approval' else '#daa520'
            arrow = FancyArrowPatch((4.5, 3.5), (7.5, 3.5),
                                   arrowstyle='->', mutation_scale=15,
                                   color=arrow_color, alpha=0.7 - i*0.2)
            ax.add_patch(arrow)
            ax.text(6, y_pos, msg.get('type', ''), fontsize=8,
                    ha='center', va='center', color=arrow_color)

    # 共识状态
    consensus_color = '#238636' if consensus else '#daa520'
    consensus_text = 'Consensus Reached' if consensus else 'Debating...'
    ax.text(6, 1.5, consensus_text, fontsize=14, fontweight='bold',
            ha='center', va='center', color=consensus_color)

    # 消息计数
    ax.text(6, 0.8, f'Messages: {len(messages)}', fontsize=10,
            ha='center', va='center', color='#8b949e')

    plt.tight_layout()

    # 转为图片
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight',
                facecolor='#0d1117', edgecolor='none')
    plt.close()
    buf.seek(0)
    return Image.open(buf)


def generate_demo_gif(output_path: str = "demo/macf_demo.gif"):
    """生成演示 GIF"""
    frames = []

    # 场景 1: 初始化
    frames.append(create_frame(
        "Step 1: Configure Task",
        agents_active=[False, False],
        messages=[],
        consensus=False,
        step=1, total_steps=6
    ))

    # 场景 2: Agent A 开始
    frames.append(create_frame(
        "Step 2: Agent A Analyzes",
        agents_active=[True, False],
        messages=[],
        consensus=False,
        step=2, total_steps=6
    ))

    # 场景 3: Agent A 提出方案
    frames.append(create_frame(
        "Step 3: Agent A Proposes",
        agents_active=[False, True],
        messages=[{"from": "agent-a", "to": "agent-b", "type": "proposal"}],
        consensus=False,
        step=3, total_steps=6
    ))

    # 场景 4: Agent B 评审
    frames.append(create_frame(
        "Step 4: Agent B Reviews",
        agents_active=[True, False],
        messages=[
            {"from": "agent-a", "to": "agent-b", "type": "proposal"},
            {"from": "agent-b", "to": "agent-a", "type": "critique"},
        ],
        consensus=False,
        step=4, total_steps=6
    ))

    # 场景 5: 多轮讨论
    frames.append(create_frame(
        "Step 5: Multi-round Debate",
        agents_active=[True, True],
        messages=[
            {"from": "agent-a", "to": "agent-b", "type": "proposal"},
            {"from": "agent-b", "to": "agent-a", "type": "critique"},
            {"from": "agent-a", "to": "agent-b", "type": "revision"},
            {"from": "agent-b", "to": "agent-a", "type": "critique"},
        ],
        consensus=False,
        step=5, total_steps=6
    ))

    # 场景 6: 达成共识
    frames.append(create_frame(
        "Step 6: Consensus Reached",
        agents_active=[False, False],
        messages=[
            {"from": "agent-a", "to": "agent-b", "type": "proposal"},
            {"from": "agent-b", "to": "agent-a", "type": "critique"},
            {"from": "agent-a", "to": "agent-b", "type": "revision"},
            {"from": "agent-b", "to": "agent-a", "type": "approval"},
            {"from": "agent-a", "to": "agent-b", "type": "approval"},
        ],
        consensus=True,
        step=6, total_steps=6
    ))

    # 保存 GIF
    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=1500,  # 每帧 1.5 秒
        loop=0,
    )
    print(f"✅ Demo GIF 已保存: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_demo_gif()
