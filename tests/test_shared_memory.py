"""测试共享记忆"""
import os
import pytest
from macf.shared_memory import SharedMemory


@pytest.fixture
def memory(tmp_path):
    memory_path = str(tmp_path / "test_memory.json")
    return SharedMemory(memory_path=memory_path)


def test_add_agreed_point(memory):
    memory.add_agreed_point("测试共识点", "agent-a")
    stats = memory.get_stats()
    assert stats["agreed_count"] == 1


def test_no_duplicate_points(memory):
    memory.add_agreed_point("测试共识点", "agent-a")
    memory.add_agreed_point("测试共识点", "agent-b")
    stats = memory.get_stats()
    assert stats["agreed_count"] == 1


def test_mark_file_read(memory):
    memory.mark_file_read("test.py", "agent-a")
    summary = memory.get_files_read_summary()
    assert "test.py" in summary
    assert "agent-a" in summary
