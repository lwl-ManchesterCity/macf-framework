# Changelog

所有版本变更记录。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [v0.5.0] - 2026-08-04

### Added
- **自动化执行** — 方案文档自动生成代码
- **代码生成器** (`executor/code_generator.py`)
  - 解析方案文档提取任务清单
  - 逐任务调用 LLM 生成代码
  - 自动写入工作区文件
- **执行 API** — `POST /api/debate/{id}/execute`
- **Web UI 执行按钮** — 一键触发代码生成
- **WebSocket 执行进度** — 实时推送执行状态

## [v0.4.0] - 2026-08-04

### Added
- **WebSocket 实时推送** (`/ws/debate/{id}`) — 无需轮询
- **全局统计端点** (`/api/stats`)
- **辩论历史列表** — 查看所有过往辩论
- **Web UI 升级** — 实时消息流

## [v0.3.0] - 2026-08-04

### Added
- **API Gateway** (FastAPI + REST API)
- **Docker 部署** (Dockerfile + docker-compose.yml)
- **Web UI** (实时监控界面)

## [v0.2.0] - 2026-08-03

### Added
- 双方共识机制
- 轮次管理模式
- 单 Agent 故障隔离
- 讨论摘要生成
- 方案质量校验

## [v0.1.0] - 2026-08-03

### Added
- 初始版本发布
- 多 Agent 辩论协作框架
