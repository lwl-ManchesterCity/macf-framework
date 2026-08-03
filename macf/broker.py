"""
MACF Broker - Redis 消息中间件

负责消息的路由、发布、订阅。
每个 Agent 订阅自己的 channel，发送时发布到目标 Agent 的 channel。
"""

import json
import redis
from typing import Optional, Callable
from .protocol import Message, MessageType


class MessageBroker:
    """基于 Redis Pub/Sub 的消息代理"""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.redis_client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
        )
        self.pubsub = self.redis_client.pubsub()
        self._connected = True
        print(f"✅ Redis 连接成功: {host}:{port}")

    def _channel_name(self, agent_id: str) -> str:
        """生成 Agent 的订阅 channel 名"""
        return f"macf:agent:{agent_id}"

    def _global_channel(self) -> str:
        """全局广播 channel"""
        return "macf:broadcast"

    def publish(self, message: Message) -> bool:
        """
        发布消息到目标 Agent 的 channel
        """
        if message.to_agent == "broadcast":
            channel = self._global_channel()
        else:
            channel = self._channel_name(message.to_agent)

        try:
            subscribers = self.redis_client.publish(channel, message.to_json())
            print(f"📤 发布消息 → {channel} ({subscribers} 个订阅者)")
            return True
        except redis.ConnectionError as e:
            print(f"❌ 发布失败: {e}")
            return False

    def subscribe(self, agent_id: str, handler: Callable[[Message], None]):
        """
        订阅 Agent 自己的 channel + 全局广播 channel
        """
        channels = [self._channel_name(agent_id), self._global_channel()]
        self.pubsub.subscribe(**{ch: self._wrap_handler(handler) for ch in channels})
        print(f"👂 Agent [{agent_id}] 已订阅: {channels}")

    def subscribe_pattern(self, pattern: str, handler: Callable[[Message], None]):
        """
        使用 Redis 模式订阅（PSUBSCRIBE）监控多个 channel
        例如: pattern="macf:agent:*" 可监控所有 Agent 的消息
        """
        self.pubsub.psubscribe(**{pattern: self._wrap_handler(handler)})
        print(f"👂 模式订阅: {pattern}")

    def _wrap_handler(self, handler: Callable[[Message], None]):
        """包装 handler，解析 JSON 消息"""
        def _handler(message):
            # 支持普通消息和模式订阅消息
            if message["type"] in ("message", "pmessage"):
                try:
                    msg = Message.from_json(message["data"])
                    print(f"🔔 [broker] 收到消息: {msg.from_agent} → {msg.to_agent} ({msg.type.value})")
                    handler(msg)
                except Exception as e:
                    print(f"❌ 消息解析失败: {e}")
        return _handler

    def listen(self, timeout: float = 1.0):
        """
        阻塞监听消息（在独立线程中运行）
        """
        try:
            message = self.pubsub.get_message(timeout=timeout)
            return message
        except Exception as e:
            print(f"❌ 监听错误: {e}")
            return None

    def start_listener(self):
        """启动后台监听线程"""
        import threading
        self._stop_event = threading.Event()
        self._listener_thread = self.pubsub.run_in_thread(
            sleep_time=0.1,
            daemon=True,
        )
        print("🎧 后台监听已启动")

    def stop_listener(self):
        """停止监听"""
        if hasattr(self, '_stop_event'):
            self._stop_event.set()
        if hasattr(self, '_listener_thread'):
            try:
                self._listener_thread.stop()
            except Exception:
                pass
            print("🛑 监听已停止")

    def close(self):
        """关闭连接"""
        # 先停止监听线程
        self.stop_listener()
        # 等待线程完全停止
        import time
        time.sleep(0.5)
        # 关闭连接
        try:
            self.pubsub.close()
        except Exception:
            pass
        try:
            self.redis_client.close()
        except Exception:
            pass
        print("🔌 Redis 连接已关闭")
