# 示例：安全代码审查

## 配置

```yaml
# config/security.yaml
task:
  name: "安全代码审查"
  scope: fullstack
  description: |
    审查工作区中的代码文件，找出所有安全漏洞。

    你的任务是：
    1. 仔细阅读代码，找出所有安全漏洞
    2. 对每个漏洞说明：漏洞类型、严重程度、攻击场景、修复建议
    3. 与对方 Agent 讨论修复方案
    4. 最终达成一致的修复方案

agents:
  - id: agent-a
    name: "安全专家"
    model: deepseek
    role: "你是一位资深安全专家，擅长 OWASP Top 10、渗透测试、代码审计。负责发现安全漏洞并提出修复建议。"
    workspace: ./workspace/agent-a
    tools: [read_file, list_files, search_code]

  - id: agent-b
    name: "开发工程师"
    model: deepseek
    role: "你是一位资深开发工程师，擅长 Python/Java、安全编码实践。负责评估漏洞的可行性和修复方案。"
    workspace: ./workspace/agent-b
    tools: [read_file, list_files, search_code]

debate:
  max_turns: 8
  consensus_keywords: ["同意", "方案通过", "可以实施", "达成共识"]
```

## 运行

```bash
python3 run_agent.py --id agent-a --config config/security.yaml
python3 run_agent.py --id agent-b --config config/security.yaml
python3 run_orchestrator.py --config config/security.yaml
```

## 预期输出

```markdown
# 安全代码审查 - 技术方案

## 1. 漏洞清单
| 编号 | 漏洞类型 | 严重程度 | 位置 | 修复建议 |
|------|---------|---------|------|---------|
| 1 | SQL 注入 | 严重 | line 15 | 参数化查询 |
| 2 | XSS | 高危 | line 23 | 输入消毒 |
...

## 2. 修复方案
...
```
