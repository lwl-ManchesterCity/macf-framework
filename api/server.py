"""
MACF API Gateway - REST API 接口

提供辩论任务的启动、监控、停止、结果获取和自动化执行。
"""

import asyncio
import uuid
import os
from datetime import datetime
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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
# 共享状态存储（用于线程间通信）
shared_states: dict[str, dict] = {}
# WebSocket 连接管理
ws_connections: dict[str, list[WebSocket]] = {}
# 全局统计
global_stats = {
    "total_debates": 0,
    "total_messages": 0,
    "total_tokens": 0,
    "total_cost_rmb": 0.0,
}


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
    status: str = "pending"  # pending/running/completed/executed/failed
    created_at: str
    updated_at: str
    messages: list[dict] = []
    result: Optional[str] = None
    error: Optional[str] = None
    error_detail: Optional[str] = None
    stats: dict = {}
    execution_result: Optional[dict] = None
    execution_error: Optional[str] = None


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
async def start_debate(config: DebateConfig):
    """启动辩论任务"""
    import threading

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

    # 在线程中启动辩论（避免阻塞事件循环）
    thread = threading.Thread(
        target=run_debate_sync,
        args=(debate_id, config),
        daemon=True,
    )
    thread.start()

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

    # 消息已直接存储在 task 中
    messages = task.messages
    stats = task.stats

    return {
        "id": task.id,
        "status": task.status,
        "config": task.config.dict(),
        "stats": stats,
        "message_count": len(messages),
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


@app.get("/api/debate/{debate_id}/execution")
async def get_execution(debate_id: str):
    """获取执行结果"""
    if debate_id not in debates:
        raise HTTPException(status_code=404, detail="辩论不存在")
    task = debates[debate_id]
    return {
        "id": debate_id,
        "status": task.status,
        "execution_result": task.execution_result,
        "execution_error": task.execution_error,
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
                "message_count": len(t.messages),
            }
            for t in sorted(debates.values(), key=lambda x: x.created_at, reverse=True)
        ]
    }


@app.get("/api/stats")
async def get_stats():
    """获取全局统计"""
    return {
        "global": global_stats,
        "active_debates": len([t for t in debates.values() if t.status == "running"]),
        "total_debates": len(debates),
    }


@app.post("/api/debate/{debate_id}/execute")
async def execute_plan(debate_id: str):
    """自动执行方案——生成代码"""
    if debate_id not in debates:
        raise HTTPException(status_code=404, detail="辩论不存在")
    task = debates[debate_id]
    if task.status not in ("completed", "completed_with_warnings"):
        raise HTTPException(status_code=400, detail="辩论未完成，无法执行")

    # 异步执行
    import asyncio
    asyncio.create_task(run_code_generation(debate_id))

    return {"id": debate_id, "status": "executing", "message": "代码生成已启动"}


@app.websocket("/ws/debate/{debate_id}")
async def websocket_endpoint(websocket: WebSocket, debate_id: str):
    """WebSocket 实时推送辩论消息"""
    await websocket.accept()

    if debate_id not in debates:
        await websocket.close(code=4004, reason="辩论不存在")
        return

    # 注册连接
    if debate_id not in ws_connections:
        ws_connections[debate_id] = []
    ws_connections[debate_id].append(websocket)

    try:
        # 先发送历史消息
        await websocket.send_json({
            "type": "history",
            "messages": debates[debate_id].messages,
        })

        # 等待新消息（通过轮询检查）
        while True:
            await asyncio.sleep(1)
            # 检查辩论是否结束
            if debates[debate_id].status in ("completed", "failed", "stopped"):
                await websocket.send_json({
                    "type": "status",
                    "status": debates[debate_id].status,
                })
                break
    except WebSocketDisconnect:
        pass
    finally:
        # 清理连接
        if debate_id in ws_connections:
            ws_connections[debate_id].remove(websocket)


async def broadcast_message(debate_id: str, message: dict):
    """向所有 WebSocket 连接广播消息"""
    if debate_id in ws_connections:
        disconnected = []
        for ws in ws_connections[debate_id]:
            try:
                await ws.send_json({
                    "type": "message",
                    "data": message,
                })
            except Exception:
                disconnected.append(ws)


async def run_code_generation(debate_id: str):
    """后台运行代码生成"""
    task = debates[debate_id]
    task.status = "executing"
    await broadcast_message(debate_id, {"type": "execution_started"})

    try:
        from executor.code_generator import CodeGenerator

        model_config = {
            "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
        }

        plan_path = "./workspace/final_plan.md"
        workspace = "./workspace"

        generator = CodeGenerator(workspace, model_config)
        result = generator.execute_plan(plan_path)

        task.execution_result = result
        task.status = "executed" if result.get("success") else "execution_failed"

        await broadcast_message(debate_id, {
            "type": "execution_completed",
            "result": result,
        })

    except Exception as e:
        task.status = "execution_failed"
        task.execution_error = str(e)
        await broadcast_message(debate_id, {
            "type": "execution_failed",
            "error": str(e),
        })
                disconnected.append(ws)
        # 清理断开的连接
        for ws in disconnected:
            ws_connections[debate_id].remove(ws)


# ==================== 后台任务 ====================

def run_debate_sync(debate_id: str, config: DebateConfig):
    """同步运行辩论（在线程中执行，避免阻塞事件循环）"""
    task = debates[debate_id]
    task.status = "running"
    task.updated_at = datetime.now().isoformat()

    try:
        # 导入 MACF 核心
        import sys
        import os
        # 添加项目根目录到 path
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from macf.orchestrator import DebateOrchestrator
        from macf.protocol import Message, MessageType
        import yaml

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

        # 注册消息监控——直接更新 task 对象
        def monitor_with_capture(msg: Message):
            # 捕获消息到 task
            msg_data = {
                "id": msg.id,
                "from": msg.from_agent,
                "to": msg.to_agent,
                "type": msg.type.value,
                "content": msg.payload.get("content", "")[:500],
                "timestamp": msg.timestamp,
            }
            task.messages.append(msg_data)
            task.stats = {
                "total_messages": len(orchestrator.debate_log),
                "agreed_points": len(orchestrator.agreed_points),
                "consensus_reached": orchestrator.consensus_reached,
                "round": getattr(orchestrator, "_current_round", 0),
            }

        orchestrator._monitor_handler = monitor_with_capture

        # 重新订阅 handler（__init__ 里已订阅原始 handler，需更新为新的）
        for agent_id in orchestrator.agents:
            orchestrator.broker.subscribe(agent_id, monitor_with_capture)

        # 运行辩论
        orchestrator.run_debate(
            task=config.description,
            starter=config.agents[0]["id"],
            responder=config.agents[1]["id"] if len(config.agents) > 1 else config.agents[0]["id"],
        )

        # 消息已在监控中直接更新到 task，无需额外同步

        # 读取结果
        plan_path = "./workspace/final_plan.md"
        if os.path.exists(plan_path):
            with open(plan_path, "r", encoding="utf-8") as f:
                task.result = f.read()

        # 更新全局统计
        global_stats["total_debates"] += 1
        global_stats["total_messages"] += len(orchestrator.debate_log)
        global_stats["total_tokens"] += getattr(orchestrator, "_total_tokens", 0)

        task.status = "completed" if orchestrator.consensus_reached else "completed_with_warnings"

        # WebSocket 推送完成通知
        asyncio.run(broadcast_message(debate_id, {
            "type": "completed",
            "status": task.status,
            "message_count": len(task.messages),
        }))

    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        import traceback
        task.error_detail = traceback.format_exc()
        traceback.print_exc()

    finally:
        task.updated_at = datetime.now().isoformat()


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
