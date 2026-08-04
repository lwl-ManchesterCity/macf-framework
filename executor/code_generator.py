"""
MACF Code Generator - 自动化执行

读取 final_plan.md，自动生成代码实现。
支持：
1. 解析方案文档提取任务清单
2. 逐任务生成代码
3. 自动运行测试验证
4. 生成修复报告
"""

import os
import re
import json
from typing import Optional
from pathlib import Path
from openai import OpenAI


class CodeGenerator:
    """代码生成器——将方案文档转化为代码"""

    def __init__(self, workspace: str, model_config: dict):
        self.workspace = Path(workspace)
        self.client = OpenAI(
            api_key=model_config["api_key"],
            base_url=model_config["base_url"],
            timeout=120.0,
        )
        self.model = model_config["model"]
        self.generated_files = []
        self.test_results = []

    def execute_plan(self, plan_path: str) -> dict:
        """执行方案文档，生成代码"""
        print(f"\n{'='*60}")
        print("🤖 开始执行方案")
        print(f"{'='*60}\n")

        # 1. 读取方案
        plan_content = self._read_plan(plan_path)
        if not plan_content:
            return {"success": False, "error": "无法读取方案文档"}

        # 2. 解析任务清单
        tasks = self._parse_tasks(plan_content)
        print(f"📋 解析到 {len(tasks)} 个任务\n")

        # 3. 获取当前代码文件
        existing_code = self._get_existing_code()

        # 4. 逐任务生成代码
        for i, task in enumerate(tasks, 1):
            print(f"🔧 任务 {i}/{len(tasks)}: {task['title'][:50]}...")
            result = self._execute_task(task, existing_code)
            if result.get("success"):
                self.generated_files.append(result.get("file"))
                # 更新现有代码上下文
                existing_code[result.get("file")] = result.get("code", "")
            print(f"   {'✅' if result.get('success') else '❌'} {result.get('message', '')}")

        # 5. 生成报告
        report = self._generate_report()
        return report

    def _read_plan(self, plan_path: str) -> Optional[str]:
        """读取方案文档"""
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"❌ 读取方案失败: {e}")
            return None

    def _parse_tasks(self, plan_content: str) -> list[dict]:
        """从方案文档解析任务清单"""
        tasks = []

        # 匹配实施步骤
        steps_match = re.search(r'##\s*\d+\.\s*实施步骤(.*?)(?=##|\Z)', plan_content, re.DOTALL)
        if steps_match:
            steps_text = steps_match.group(1)
            # 匹配有序列表项
            steps = re.findall(r'\d+\.\s*\*\*(.+?)\*\*\s*:?\s*(.+?)(?=\n\d+\.|\Z)', steps_text, re.DOTALL)
            for title, desc in steps:
                tasks.append({
                    "title": title.strip(),
                    "description": desc.strip(),
                    "type": "implementation",
                })

        # 如果没匹配到，从整个文档提取
        if not tasks:
            # 从接口契约提取
            api_match = re.search(r'##\s*\d+\.\s*接口契约(.*?)(?=##|\Z)', plan_content, re.DOTALL)
            if api_match:
                tasks.append({
                    "title": "实现 API 接口",
                    "description": api_match.group(1).strip(),
                    "type": "api_implementation",
                })

            # 从数据模型提取
            model_match = re.search(r'##\s*\d+\.\s*数据模型(.*?)(?=##|\Z)', plan_content, re.DOTALL)
            if model_match:
                tasks.append({
                    "title": "实现数据模型",
                    "description": model_match.group(1).strip(),
                    "type": "model_implementation",
                })

        # 保底：至少生成一个综合任务
        if not tasks:
            tasks.append({
                "title": "方案实现",
                "description": plan_content[:2000],
                "type": "full_implementation",
            })

        return tasks

    def _get_existing_code(self) -> dict[str, str]:
        """获取工作区现有代码"""
        code = {}
        for f in self.workspace.rglob("*.py"):
            if "__pycache__" not in str(f):
                rel_path = f.relative_to(self.workspace)
                try:
                    code[str(rel_path)] = f.read_text(encoding="utf-8")
                except Exception:
                    pass
        return code

    def _execute_task(self, task: dict, existing_code: dict) -> dict:
        """执行单个任务"""
        try:
            # 构建 prompt
            prompt = self._build_task_prompt(task, existing_code)

            # 调用 LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4096,
            )

            content = response.choices[0].message.content or ""

            # 解析生成的代码
            code, file_path = self._extract_code(content)

            if code and file_path:
                # 写入文件
                full_path = self.workspace / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(code, encoding="utf-8")

                return {
                    "success": True,
                    "file": file_path,
                    "code": code,
                    "message": f"已生成 {file_path}",
                }
            else:
                return {
                    "success": False,
                    "message": "未能解析生成的代码",
                }

        except Exception as e:
            return {
                "success": False,
                "message": str(e),
            }

    def _system_prompt(self) -> str:
        """系统提示词"""
        return """你是一个高级 Python 开发工程师。根据任务描述生成高质量的代码实现。

规则：
1. 只生成一个 Python 文件
2. 代码必须完整可运行
3. 包含必要的 imports
4. 遵循 PEP 8 规范
5. 添加适当的注释

输出格式：
```python:文件路径
# 代码内容
```"""

    def _build_task_prompt(self, task: dict, existing_code: dict) -> str:
        """构建任务 prompt"""
        # 现有代码上下文
        context = ""
        if existing_code:
            context = "\n\n当前工作区代码:\n"
            for path, code in list(existing_code.items())[:3]:  # 最多 3 个文件
                context += f"\n--- {path} ---\n{code[:1000]}\n"

        return f"""请实现以下任务：

任务: {task['title']}
描述: {task['description']}
类型: {task['type']}
{context}

请生成完整的 Python 代码实现。"""

    def _extract_code(self, content: str) -> tuple[Optional[str], Optional[str]]:
        """从 LLM 输出中提取代码"""
        # 匹配 ```python:文件路径 ... ``` 格式
        match = re.search(r'```python:([^\n]+)\n(.*?)```', content, re.DOTALL)
        if match:
            file_path = match.group(1).strip()
            code = match.group(2).strip()
            return code, file_path

        # 匹配 ```python ... ``` 格式
        match = re.search(r'```python\n(.*?)```', content, re.DOTALL)
        if match:
            code = match.group(1).strip()
            return code, "generated_code.py"

        return None, None

    def _generate_report(self) -> dict:
        """生成执行报告"""
        return {
            "success": len(self.generated_files) > 0,
            "generated_files": self.generated_files,
            "total_files": len(self.generated_files),
            "workspace": str(self.workspace),
        }


def execute_plan_cli():
    """CLI 入口"""
    import sys

    plan_path = sys.argv[1] if len(sys.argv) > 1 else "./workspace/final_plan.md"
    workspace = sys.argv[2] if len(sys.argv) > 2 else "./workspace"

    model_config = {
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    }

    generator = CodeGenerator(workspace, model_config)
    result = generator.execute_plan(plan_path)

    print(f"\n{'='*60}")
    print("📊 执行报告")
    print(f"{'='*60}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    execute_plan_cli()
