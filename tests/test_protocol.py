"""测试消息协议"""
import pytest
from macf.protocol import Message, MessageType


def test_message_creation():
    msg = Message(
        from_agent="agent-a",
        to_agent="agent-b",
        msg_type=MessageType.PROPOSAL,
        payload={"content": "test"}
    )
    assert msg.from_agent == "agent-a"
    assert msg.to_agent == "agent-b"
    assert msg.type == MessageType.PROPOSAL
    assert msg.id.startswith("msg-")


def test_message_serialization():
    msg = Message(
        from_agent="agent-a",
        to_agent="agent-b",
        msg_type=MessageType.PROPOSAL,
        payload={"content": "test"}
    )
    json_str = msg.to_json()
    restored = Message.from_json(json_str)
    assert restored.from_agent == msg.from_agent
    assert restored.to_agent == msg.to_agent
    assert restored.type == msg.type
