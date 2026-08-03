"""
MACF Shared Memory - 共享记忆机制

两个 Agent 通过共享文件来记录已达成的共识和讨论进度。
避免重复讨论已确认的点，减少上下文丢失。
"""

import json
import os
from typing import List, Dict, Any
from datetime import datetime


class SharedMemory:
    """共享记忆——Agent 之间的桥梁"""

    def __init__(self, memory_path: str = "./workspace/shared_memory.json"):
        self.memory_path = memory_path
        self._ensure_file()

    def _ensure_file(self):
        """确保文件存在"""
        os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
        if not os.path.exists(self.memory_path):
            self._save({
                "agreed_points": [],
                "disputed_points": [],
                "files_read": {},
                "message_count": 0,
                "last_update": None,
            })

    def _load(self) -> dict:
        """读取记忆"""
        try:
            with open(self.memory_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {
                "agreed_points": [],
                "disputed_points": [],
                "files_read": {},
                "message_count": 0,
                "last_update": None,
            }

    def _save(self, data: dict):
        """保存记忆"""
        data["last_update"] = datetime.now().isoformat()
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_agreed_point(self, point: str, agreed_by: str = None):
        """添加已达成的共识"""
        data = self._load()
        entry = {
            "point": point,
            "agreed_by": agreed_by,
            "timestamp": datetime.now().isoformat(),
        }
        # 避免重复
        existing_points = [p["point"] for p in data["agreed_points"]]
        if point not in existing_points:
            data["agreed_points"].append(entry)
            self._save(data)
            self._save(data)

    def add_disputed_point(self, point: str, reason: str = None):
        """添加有争议的点"""
        data = self._load()
        entry = {
            "point": point,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        }
        data["disputed_points"].append(entry)
        self._save(data)

    def mark_file_read(self, filename: str, read_by: str):
        """标记文件已被读取"""
        data = self._load()
        if filename not in data["files_read"]:
            data["files_read"][filename] = []
        if read_by not in data["files_read"][filename]:
            data["files_read"][filename].append(read_by)
            self._save(data)

    def increment_message_count(self):
        """增加消息计数"""
        data = self._load()
        data["message_count"] = data.get("message_count", 0) + 1
        self._save(data)

    def get_agreed_summary(self) -> str:
        """获取共识摘要（注入到 Agent 消息中）"""
        data = self._load()
        if not data["agreed_points"]:
            return "（暂无已确认的共识）"

        summary = "已确认的共识点：\n"
        for i, entry in enumerate(data["agreed_points"], 1):
            by = f" [{entry.get('agreed_by', 'unknown')}]" if entry.get('agreed_by') else ""
            summary += f"{i}. {entry['point']}{by}\n"
        return summary

    def get_disputed_summary(self) -> str:
        """获取争议摘要"""
        data = self._load()
        if not data["disputed_points"]:
            return "（暂无争议点）"

        summary = "待解决的争议：\n"
        for i, entry in enumerate(data["disputed_points"], 1):
            reason = f" - {entry['reason']}" if entry.get('reason') else ""
            summary += f"{i}. {entry['point']}{reason}\n"
        return summary

    def get_files_read_summary(self) -> str:
        """获取文件读取记录"""
        data = self._load()
        if not data["files_read"]:
            return "（无文件读取记录）"

        summary = "已读取的文件：\n"
        for fname, readers in data["files_read"].items():
            summary += f"- {fname}: {', '.join(readers)} 已读\n"
        return summary

    def get_full_context(self) -> str:
        """获取完整上下文（注入到 Agent 系统提示中）"""
        data = self._load()
        context = f"""=== 共享记忆 ===
{self.get_agreed_summary()}

{self.get_disputed_summary()}

{self.get_files_read_summary()}

总消息数: {data.get('message_count', 0)}
最后更新: {data.get('last_update', 'unknown')}
================"""
        return context

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        data = self._load()
        return {
            "agreed_count": len(data["agreed_points"]),
            "disputed_count": len(data["disputed_points"]),
            "files_read_count": len(data["files_read"]),
            "message_count": data.get("message_count", 0),
        }
