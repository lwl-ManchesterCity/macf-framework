"""
MACF API Gateway - REST API 接口

提供辩论任务的启动、监控、停止和结果获取。
"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="MACF API",
    description="Multi-Agent Collaboration Framework - REST API",
    version="0.3.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 内存存储（生产环境用 Redis/DB）
debates: dict[str, "DebateTask"] = {}


# ==================== 数据模型 ====================

class DebateConfig(BaseModel):
    """辩论配置"""
    task_name: str = Field(..., description="任务名称")
    scope: str = Field("fullstack", description="范围: backend/frontend/fullstack")
    description: str = Field(..., description="任务描述")
    max_turns: int = Field(6, description="最大轮次")
    agents: list[dict] = Field(..., description="Agent 配置列表")


class DebateTask(BaseModel):
    """辩论任务"""
    id: str
    config: DebateConfig
    status: str = "pending"  # pending/running/completed/failed
    created_at: str
    updated_at: str
    messages: list[dict] = []
    result: Optional[str] = None
    error: Optional[str] = None
    stats: dict = {}


class DebateResponse(BaseModel):
    """辩论响应"""
    id: str
    status: str
    created_at: str
    stats: dict = {}


# ==================== API 端点 ====================

@app.get("/")
async def root():
    """API 根路径"""
    return {
        "name": "MACF API",
        "version": "0.3.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.post("/api/debate/start", response_model=DebateResponse)
async def start_debate(config: DebateConfig, background_tasks: BackgroundTasks):
    """启动辩论任务"""
    debate_id = f"debate-{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()

    task = DebateTask(
        id=debate_id,
        config=config,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    debates[debate_id] = task

    # 后台启动辩论
    background_tasks.add_task(run_debate_task, debate_id, config)

    return DebateResponse(
        id=debate_id,
        status="pending",
        created_at=now,
    )


@app.get("/api/debate/{debate_id}")
async def get_debate(debate_id: str):
    """获取辩论状态"""
    if debate_id not in debates:
        raise HTTPException(status_code=404, detail="辩论不存在")
    task = debates[debate_id]
    return {
        "id": task.id,
        "status": task.status,
        "config": task.config.dict(),
        "stats": task.stats,
        "message_count": len(task.messages),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


@app.get("/api/debate/{debate_id}/messages")
async def get_messages(debate_id: str):
    """获取辩论消息流"""
    if debate_id not in debates:
        raise HTTPException(status_code=404, detail="辩论不存在")
    return debates[debate_id].messages


@app.get("/api/debate/{debate_id}/result")
async def get_result(debate_id: str):
    """获取辩论结果"""
    if debate_id not in debates:
        raise HTTPException(status_code=404, detail="辩论不存在")
    task = debates[debate_id]
    if task.status != "completed":
        raise HTTPException(status_code=400, detail=f"辩论未完成 (当前: {task.status})")
    return {
        "id": debate_id,
        "result": task.result,
        "stats": task.stats,
    }


@app.post("/api/debate/{debate_id}/stop")
async def stop_debate(debate_id: str):
    """停止辩论"""
    if debate_id not in debates:
        raise HTTPException(status_code=404, detail="辩论不存在")
    task = debates[debate_id]
    if task.status == "running":
        task.status = "stopped"
        task.updated_at = datetime.now().isoformat()
    return {"id": debate_id, "status": task.status}


@app.get("/api/debates")
async def list_debates():
    """列出所有辩论"""
    return {
        "debates": [
            {
                "id": t.id,
                "status": t.status,
                "task_name": t.config.task_name,
                "created_at": t.created_at,
            }
            for t in debates.values()
        ]
    }


# ==================== 后台任务 ====================

async def run_debate_task(debate_id: str, config: DebateConfig):
    """后台运行辩论"""
    task = debates[debate_id]
    task.status = "running"
    task.updated_at = datetime.now().isoformat()

    try:
        # 导入 MACF 核心
        import sys
        sys.path.insert(0, "..")
        from macf.orchestrator import DebateOrchestrator
        from macf.protocol import MessageType
        import yaml
        import os

        # 构建配置
        yaml_config = {
            "task": {
                "name": config.task_name,
                "scope": config.scope,
                "description": config.description,
            },
            "broker": {
                "host": os.environ.get("REDIS_HOST", "localhost"),
                "port": int(os.environ.get("REDIS_PORT", 6379)),
            },
            "models": {
                "deepseek": {
                    "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
                    "base_url": "https://api.deepseek.com",
                    "model": "deepseek-chat",
                }
            },
            "agents": config.agents,
            "debate": {
                "max_turns": config.max_turns,
                "consensus_keywords": ["同意", "方案通过", "可以实施", "达成共识"],
            },
        }

        # 创建协调器
        orchestrator = DebateOrchestrator(yaml_config)

        # 注册消息监控
        original_monitor = orchestrator._monitor_handler

        def monitor_with_capture(msg: Message):
            original_monitor(msg)
            # 捕获消息到 API
            task.messages.append({
                "id": msg.id,
                "from": msg.from_agent,
                "to": msg.to_agent,
                "type": msg.type.value,
                "content": msg.payload.get("content", "")[:500],
                "timestamp": msg.timestamp,
            })
            task.stats = {
                "total_messages": len(orchestrator.debate_log),
                "agreed_points": len(orchestrator.agreed_points),
                "consensus_reached": orchestrator.consensus_reached,
            }

        orchestrator._monitor_handler = monitor_with_capture

        # 运行辩论
        orchestrator.run_debate(
            task=config.description,
            starter=config.agents[0]["id"],
            responder=config.agents[1]["id"] if len(config.agents) > 1 else config.agents[0]["id"],
        )

        # 读取结果
        plan_path = "./workspace/final_plan.md"
        if os.path.exists(plan_path):
            with open(plan_path, "r", encoding="utf-8") as f:
                task.result = f.read()

        task.status = "completed" if orchestrator.consensus_reached else "completed_with_warnings"

    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        import traceback
        traceback.print_exc()

    finally:
        task.updated_at = datetime.now().isoformat()


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
