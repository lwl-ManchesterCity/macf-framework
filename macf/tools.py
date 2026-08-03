"""
MACF Tools - Agent 可用的工具集

框架拦截模型的 Function Call，在本地执行对应操作，将结果返回给模型。
"""

import os
import re
import subprocess
from typing import Optional


class ToolExecutor:
    """工具执行器 - 沙盒内文件操作和命令执行"""

    def __init__(self, workspace: str):
        """
        Args:
            workspace: 工作区根目录，所有操作限制在此目录内
        """
        self.workspace = os.path.abspath(workspace)
        os.makedirs(self.workspace, exist_ok=True)
        print(f"📁 工作区: {self.workspace}")

    def _safe_path(self, path: str) -> str:
        """确保路径在工作区内（防止目录穿越）"""
        full_path = os.path.abspath(os.path.join(self.workspace, path))
        if not full_path.startswith(self.workspace):
            raise PermissionError(f"⛔ 路径越界: {path}")
        return full_path

    def read_file(self, path: str) -> str:
        """读取工作区文件内容"""
        try:
            safe_path = self._safe_path(path)
            with open(safe_path, "r", encoding="utf-8") as f:
                content = f.read()
            print(f"📖 读取文件: {path} ({len(content)} 字符)")
            return content
        except FileNotFoundError:
            return f"❌ 文件不存在: {path}"
        except Exception as e:
            return f"❌ 读取失败: {e}"

    def write_file(self, path: str, content: str) -> str:
        """写入内容到文件"""
        try:
            safe_path = self._safe_path(path)
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✏️ 写入文件: {path} ({len(content)} 字符)")
            return f"✅ 文件已写入: {path}"
        except Exception as e:
            return f"❌ 写入失败: {e}"

    def list_files(self) -> str:
        """列出工作区文件树"""
        try:
            files = []
            for root, dirs, filenames in os.walk(self.workspace):
                # 隐藏目录跳过
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for fname in filenames:
                    if not fname.startswith("."):
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, self.workspace)
                        files.append(rel)
            result = "\n".join(sorted(files)) if files else "(空工作区)"
            print(f"📂 列出文件: {len(files)} 个")
            return result
        except Exception as e:
            return f"❌ 列出文件失败: {e}"

    def run_command(self, command: str) -> str:
        """在终端执行命令（限制在工作区内）"""
        # 安全黑名单 - 禁止危险命令
        dangerous_patterns = [
            r"\brm\s+-rf\s+/",
            r"\bchmod\s+777",
            r"\bnc\b.*-e",
            r"\bcurl\b.*\|.*sh",
            r"\bwget\b.*\|.*sh",
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, command):
                return f"⛔ 命令被安全策略禁止: {command}"

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR] {result.stderr}"
            if result.returncode != 0:
                output += f"\n[EXIT CODE] {result.returncode}"
            print(f"⚡ 执行命令: {command[:50]}{'...' if len(command) > 50 else ''}")
            return output.strip() or "(无输出)"
        except subprocess.TimeoutExpired:
            return "⛔ 命令执行超时 (30s)"
        except Exception as e:
            return f"❌ 命令执行失败: {e}"

    def search_code(self, pattern: str, file_type: str = ".py") -> str:
        """在代码中搜索内容（正则）"""
        try:
            results = []
            for root, dirs, filenames in os.walk(self.workspace):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for fname in filenames:
                    if fname.endswith(file_type):
                        full = os.path.join(root, fname)
                        with open(full, "r", encoding="utf-8") as f:
                            for i, line in enumerate(f, 1):
                                if re.search(pattern, line):
                                    rel = os.path.relpath(full, self.workspace)
                                    results.append(f"{rel}:{i}: {line.rstrip()}")
            result = "\n".join(results[:50])  # 限制结果数量
            if len(results) > 50:
                result += f"\n... (共 {len(results)} 条，显示前 50)"
            print(f"🔍 搜索 '{pattern}': {len(results)} 条结果")
            return result if results else "(无匹配)"
        except Exception as e:
            return f"❌ 搜索失败: {e}"

    def get_tool_definitions(self) -> list:
        """
        返回 OpenAI Function Calling 格式的工具定义
        用于传给模型的 tools 参数
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "读取工作区中的文件内容",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "文件相对路径（相对于工作区）",
                            }
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "写入内容到工作区的文件",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "文件相对路径",
                            },
                            "content": {
                                "type": "string",
                                "description": "要写入的文件内容",
                            },
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "列出工作区中的所有文件",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "在终端执行 Shell 命令",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "要执行的 Shell 命令",
                            }
                        },
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_code",
                    "description": "在代码中使用正则表达式搜索内容",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "正则表达式模式",
                            },
                            "file_type": {
                                "type": "string",
                                "description": "文件扩展名过滤，如 .py, .js, .ts",
                                "default": ".py",
                            },
                        },
                        "required": ["pattern"],
                    },
                },
            },
        ]

    def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """根据工具名执行对应操作"""
        tool_map = {
            "read_file": lambda: self.read_file(arguments.get("path", "")),
            "write_file": lambda: self.write_file(
                arguments.get("path", ""), arguments.get("content", "")
            ),
            "list_files": lambda: self.list_files(),
            "run_command": lambda: self.run_command(arguments.get("command", "")),
            "search_code": lambda: self.search_code(
                arguments.get("pattern", ""),
                arguments.get("file_type", ".py"),
            ),
        }

        if tool_name not in tool_map:
            return f"❌ 未知工具: {tool_name}"

        try:
            return tool_map[tool_name]()
        except PermissionError as e:
            return str(e)
        except Exception as e:
            return f"❌ 工具执行错误: {e}"
