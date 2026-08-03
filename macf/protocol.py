"""
MACF Protocol - 消息协议定义
"""

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any


class MessageType(str, Enum):
    # 任务相关
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_REVIEW = "task_review"

    # Debate 相关
    PROPOSAL = "proposal"
    CRITIQUE = "critique"
    REVISION = "revision"
    APPROVAL = "approval"
    REJECTION = "rejection"

    # 控制类
    HEARTBEAT = "heartbeat"
    ERROR = "error"


class Message:
    """MACF 消息对象"""

    def __init__(
        self,
        from_agent: str,
        to_agent: str,
        msg_type: MessageType,
        payload: dict = None,
        msg_id: str = None,
        reply_to: str = None,
    ):
        self.id = msg_id or f"msg-{uuid.uuid4().hex[:8]}"
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.type = msg_type
        self.payload = payload or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.reply_to = reply_to

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        data = json.loads(json_str)
        msg = cls(
            from_agent=data["from_agent"],
            to_agent=data["to_agent"],
            msg_type=MessageType(data["type"]),
            payload=data.get("payload", {}),
            msg_id=data.get("id"),
            reply_to=data.get("reply_to"),
        )
        msg.timestamp = data.get("timestamp", msg.timestamp)
        return msg

    def __repr__(self):
        return f"[{self.type.value}] {self.from_agent} → {self.to_agent}: {self.payload.get('summary', '')}"
